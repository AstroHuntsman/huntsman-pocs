import os
import time
from contextlib import suppress
from astropy import units as u

from panoptes.utils import error
from panoptes.utils.utils import get_quantity_value
from panoptes.utils.time import current_time, wait_for_events, CountdownTimer

from panoptes.pocs.observatory import Observatory
from panoptes.pocs.scheduler.observation.bias import BiasObservation

from huntsman.pocs.utils.logger import get_logger
from huntsman.pocs.guide.bisque import Guide
from huntsman.pocs.archive.utils import remove_empty_directories
from huntsman.pocs.scheduler.observation.dark import DarkObservation
from huntsman.pocs.utils.flats import FlatFieldSequence, make_flat_field_observation


class HuntsmanObservatory(Observatory):

    def __init__(self, with_autoguider=True, hdr_mode=False, take_flats=True, logger=None,
                 *args, **kwargs):
        """Huntsman POCS Observatory

        Args:
            with_autoguider (bool, optional): If autoguider is attached, defaults to True.
            hdr_mode (bool, optional): If pics should be taken in HDR mode, defaults to False.
            take_flats (bool, optional): If flat field images should be taken, defaults to True.
            logger (logger, optional): The logger instance. If not provided, use default Huntsman
                logger.
            *args: Parsed to Observatory init function.
            **kwargs: Parsed to Observatory init function.
        """
        if not logger:
            logger = get_logger()

        # Load the config file
        try:
            assert os.getenv('HUNTSMAN_POCS') is not None
        except AssertionError:
            raise RuntimeError("The HUNTSMAN_POCS environment variable is not set.")

        super().__init__(logger=logger, *args, **kwargs)

        self._has_hdr_mode = hdr_mode
        self._has_autoguider = with_autoguider

        self.flat_fields_required = take_flats

        # Focusing
        self.last_coarse_focus_time = None
        self.last_coarse_focus_temp = None
        self._coarse_focus_interval = self.get_config('focusing.coarse.interval_hours', 1) * u.hour
        self._coarse_focus_filter = self.get_config('focusing.coarse.filter_name')
        self._coarse_focus_temptol = self.get_config('focusing.coarse.temp_tol_deg', 5) * u.Celsius

        self.last_fine_focus_time = None
        self.last_fine_focus_temp = None
        self._fine_focus_interval = self.get_config('focusing.fine.interval_hours', 1) * u.hour
        self._fine_focus_temptol = self.get_config('focusing.fine.temp_tol_deg', 5) * u.Celsius

        if self.has_autoguider:
            self.logger.info("Setting up autoguider")
            try:
                self._create_autoguider()
            except Exception as e:
                self._has_autoguider = False
                self.logger.warning(f"Problem setting autoguider, continuing without: {e!r}")

        # Hack solution to the observatory not knowing whether it is safe or not
        # This can be overridden when creating the HuntsmanPOCS instance
        self._safety_func = None

    # Properties

    @property
    def has_hdr_mode(self):
        """ Does camera support HDR mode

        Returns:
            bool: HDR enabled, default False
        """
        return self._has_hdr_mode

    @property
    def has_autoguider(self):
        """ Does camera have attached autoguider

        Returns:
            bool: True if has autoguider
        """
        return self._has_autoguider

    @property
    def coarse_focus_required(self):
        """ Return True if we should do a coarse focus. """
        return self._focus_required(coarse=True)

    @property
    def fine_focus_required(self):
        """ Return True if we should do a fine focus. """
        return self._focus_required()

    @property
    def past_midnight(self):
        """Check if it's morning, useful for going into either morning or evening flats."""

        # Get the time of the nearest midnight to now
        midnight = self.observer.midnight(current_time(), which='nearest')

        # If the nearest midnight is in the past, it's the morning...
        return midnight < current_time()

    @property
    def temperature(self):
        """ Return the ambient temperature. """
        temp = None
        try:
            reading = self.db.get_current("weather")["data"]["ambient_temp_C"]
            temp = get_quantity_value(reading, u.Celsius) * u.Celsius
        except (KeyError, TypeError) as err:
            self.logger.warning(f"Unable to determine temperature: {err!r}")
        return temp

    # Methods

    def initialize(self):
        """Initialize the observatory and connected hardware """
        super().initialize()

        if self.has_autoguider:
            self.logger.debug("Connecting to autoguider")
            self.autoguider.connect()

    def analyze_recent(self):
        """Analyze the most recent exposure.

        This is a small wrapper around the POCS version which just ensures that
        there is a "pointing" image to use as a reference for solving.

        Returns:
            dict: Offset information
        """
        # Set the first image as our pointing image.
        if self.current_observation.pointing_image is None:
            image_id, file_path = self.current_observation.first_exposure
            self.current_observation.pointing_images[image_id] = file_path
            self.logger.debug(f'Pointing image set to {self.current_observation.pointing_image}')

        # Now call the main analyze
        if self.get_config('observations.analyze_recent_offset', default=True):
            super().analyze_recent()

        return self.current_offset_info

    def autofocus_cameras(self, coarse=False, filter_name=None, default_timeout=900,
                          blocking=True, **kwargs):
        """ Override autofocus_cameras to update the last focus time and move filterwheels.
        Args:
            coarse (bool, optional): Perform coarse focus? Default False.
            filter_name (str, optional): The filter name to focus with. If None (default), will
                attempt to get from config, by default using the coarse focus filter.
            *args, **kwargs: Parsed to `pocs.observatory.Observatory.autofocus_cameras`.
        Returns:
            threading.Event: The autofocus event.
        """
        focus_type = "coarse" if coarse else "fine"

        # Choose the filter to focus with
        # TODO: Move this logic to the camera level
        if filter_name is None:
            if coarse:
                filter_name = self._coarse_focus_filter
            else:
                try:
                    filter_name = self.current_observation.filter_name
                except AttributeError:
                    filter_name = self._coarse_focus_filter
                    self.logger.warning("Unable to retrieve filter name from current observation."
                                        f" Defaulting to coarse focus filter ({filter_name}).")

        # Start the autofocus sequences
        # NOTE: The FW move is handled implicitly
        self.logger.info(f"Starting {focus_type} autofocus sequence.")
        events = super().autofocus_cameras(coarse=coarse, filter_name=filter_name, **kwargs)

        # Wait for sequences to finish
        if blocking:
            timeout = self.get_config(f"focusing.{focus_type}.timeout", default_timeout)
            if not wait_for_events(list(events.values()), timeout=timeout):
                raise error.Timeout(f"Timeout of {timeout} reached while waiting for fine focus.")

        # Update last focus time
        setattr(self, f"last_{focus_type}_focus_time", current_time())

        # Update last focus temperature
        setattr(self, f"last_{focus_type}_focus_temp", self.temperature)

        return events

    def cleanup_observations(self, *args, **kwargs):
        """ Override method to remove empty directories. Called in housekeeping state."""
        super().cleanup_observations(*args, **kwargs)

        self.logger.info("Removing empty directories in images directory.")
        images_dir = self.get_config("directories.images")
        remove_empty_directories(images_dir)

        self.logger.info("Removing empty directories in archive directory.")
        archive_dir = self.get_config("directories.archive")
        remove_empty_directories(archive_dir)

    def take_flat_fields(self, cameras=None, **kwargs):
        """ Take flat fields for each camera in each filter, respecting filter order.
        Args:
            cameras (dict): Dict of cam_name: camera pairs. If None (default), use all cameras.
            **kwargs: Overrides config entries under `calibs.flat`.
        """
        if cameras is None:
            cameras = self.cameras

        # Load the flat field config, allowing overrides from kwargs
        flat_config = self.get_config('calibs.flat', default=dict())
        flat_config.update(kwargs)

        # Specify filter order
        filter_order = flat_config['filter_order'].copy()
        if self.past_midnight:  # If it's the morning, order is reversed
            filter_order.reverse()

        # Take flat fields in each filter
        for filter_name in filter_order:

            self.assert_safe(horizon="flat")

            # Get a dict of cameras that have this filter
            cameras_with_filter = {}
            for cam_name, cam in cameras.items():
                if cam.filterwheel is None:
                    if cam.filter_type == filter_name:
                        cameras_with_filter[cam_name] = cam
                elif filter_name in cam.filterwheel.filter_names:
                    cameras_with_filter[cam_name] = cam

            # Go to next filter if there are no cameras with this one
            if not cameras_with_filter:
                self.logger.warning(f'No cameras found with {filter_name} filter.')
                continue

            # Get the flat field observation
            observation = make_flat_field_observation(self.earth_location, filter_name=filter_name)
            observation.seq_time = current_time(flatten=True)

            # Take the flats for each camera in this filter
            self.logger.info(f'Taking flat fields in {filter_name} filter.')
            autoflat_config = flat_config.get("autoflats", {})
            self._take_autoflats(cameras_with_filter, observation, **autoflat_config)

        self.logger.info('Finished flat-fielding.')

    def activate_camera_cooling(self):
        """
        Activate camera cooling for all cameras.
        """
        self.logger.debug('Activating camera cooling for all cameras.')
        for cam in self.cameras.values():
            if cam.is_cooled_camera:
                cam.cooling_enabled = True

    def deactivate_camera_cooling(self):
        """
        Deactivate camera cooling for all cameras.
        """
        self.logger.debug('Deactivating camera cooling for all cameras.')
        for cam in self.cameras.values():
            if cam.is_cooled_camera:
                cam.cooling_enabled = False

    def prepare_cameras(self, sleep=60, max_attempts=5, require_all_cameras=False):
        """
        Make sure cameras are all cooled and ready.

        Arguments:
            sleep (float): Time in seconds to sleep between checking readiness. Default 60.
            max_attempts (int): Maximum number of ready checks. See `require_all_cameras`.
            require_all_cameras (bool): `True` if all cameras are required to be ready.
                If `True` and max_attempts is reached, a `PanError` will be raised. If `False`,
                any camera that has failed to become ready will be dropped from the Observatory.
        """
        # Make sure camera cooling is enabled
        self.activate_camera_cooling()

        # Wait for cameras to be ready
        n_cameras = len(self.cameras)
        num_cameras_ready = 0
        cameras_to_drop = []
        self.logger.debug('Waiting for cameras to be ready.')
        for i in range(1, max_attempts + 1):

            num_cameras_ready = 0
            for cam_name, cam in self.cameras.items():

                if cam.is_ready:
                    num_cameras_ready += 1
                    continue

                # If max attempts have been reached...
                if i == max_attempts:
                    msg = f'Max attempts reached while waiting for {cam_name} to be ready.'

                    # Raise PanError if we need all cameras
                    if require_all_cameras:
                        raise error.PanError(msg)

                    # Drop the camera if we don't need all cameras
                    else:
                        self.logger.error(msg)
                        cameras_to_drop.append(cam_name)

            # Terminate loop if all cameras are ready
            self.logger.debug(f'Number of ready cameras after {i} of {max_attempts} checks:'
                              f' {num_cameras_ready} of {n_cameras}.')
            if num_cameras_ready == n_cameras:
                self.logger.debug('All cameras are ready.')
                break
            elif i < max_attempts:
                self.logger.debug('Not all cameras are ready yet, '
                                  f'waiting another {sleep} seconds before checking again.')
                time.sleep(sleep)

        # Remove cameras that didn't become ready in time
        # This must be done outside of the main loop to avoid a RuntimeError
        for cam_name in cameras_to_drop:
            self.logger.debug(f'Removing {cam_name} from {self} for not being ready.')
            self.remove_camera(cam_name)

        # Raise a `PanError` if no cameras are ready.
        if num_cameras_ready == 0:
            raise error.PanError('No cameras ready after maximum attempts reached.')

    def take_observation_block(self, observation, cameras=None, timeout=60 * u.second,
                               remove_on_error=False, skip_focus=False, safety_kwargs=None,
                               skip_slew=False):
        """ Macro function to take an observation block.
        This function will perform:
            - slewing (when necessary)
            - fine focusing (when necessary)
            - observation exposures
            - safety checking
        Args:
            observation (Observation): The observation object.
            cameras (dict, optional): Dict of cam_name: camera pairs. If None (default), use all
                cameras.
            timeout (float, optional): The timeout in addition to the exposure time. Default 60s.
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
            skip_slew (bool, optional): If True, do not attempt to slew the telescope. Default
                False.
            **safety_kwargs (dict, optional): Extra kwargs to be parsed to safety function.
        Raises:
            RuntimeError: If safety check fails.
        """
        if cameras is None:
            cameras = self.cameras

        safety_kwargs = {} if safety_kwargs is None else safety_kwargs
        self.assert_safe(**safety_kwargs)

        # Set the sequence time of the observation
        if not hasattr(observation, "seq_time"):
            observation.seq_time = current_time(flatten=True)
        elif observation.seq_time is None:
            observation.seq_time = current_time(flatten=True)

        headers = self.get_standard_headers(observation=observation)

        # Take the observation block
        current_field = None
        while not observation.set_is_finished:

            # Check safety
            self.assert_safe(**safety_kwargs)

            # Check if we need to slew again
            if current_field is None:
                slew_to_target = True
            elif current_field != observation.field:
                slew_to_target = True
            else:
                slew_to_target = False

            # Perform the slew if necessary
            if slew_to_target and not skip_slew:
                self.slew_to_observation(observation)
                current_field = observation.field

            # Check safety again
            self.assert_safe(**safety_kwargs)

            # Focus the cameras if necessary
            if not skip_focus and (self.fine_focus_required or observation.current_exp_num == 0):
                self.autofocus_cameras(blocking=True, filter_name=observation.filter_name)

            # Check safety again
            self.assert_safe(**safety_kwargs)

            # Set the start time for this batch of exposures
            headers['start_time'] = current_time(flatten=True)

            # Start the exposures and get events
            # TODO: Replace with concurrent.futures
            self.logger.info(f"Taking exposure {observation.current_exp_num}/{observation.min_nexp}"
                             f" for {observation}.")

            events = {}
            for cam_name, camera in cameras.items():
                try:
                    events[cam_name] = camera.take_observation(observation, headers=headers)
                except error.PanError as err:
                    self.logger.error(f"{err!r}")
                    self.logger.warning("Continuing with observation block after error on"
                                        f" {cam_name}.")

            # Wait for the exposures (blocking)
            # TODO: Use same timeout as camera client
            try:
                self._wait_for_camera_events(events, duration=observation.exptime + timeout,
                                             remove_on_error=remove_on_error, **safety_kwargs)
            except error.Timeout as err:
                self.logger.error(f"{err!r}")
                self.logger.warning("Continuing with observation block after error.")

            # Explicitly mark the observation as complete
            with suppress(AttributeError):
                observation.mark_exposure_complete()

    def take_dark_observation(self, bias=False, **kwargs):
        """ Take a bias observation block on each camera (blocking).
        Args:
            bias (bool, optional): If True, take Bias observation instead of dark observation.
                Default: False.
            **kwargs: Parsed to `self.take_observation_block`.
        """
        # Move telescope to park position
        if not self.mount.is_parked:
            self.logger.info("Moving telescope to park position for dark observation.")
            self.mount.park()

        # Create the observation
        # Keep the mount where it is since we are just taking darks
        position = self.mount.get_current_coordinates()
        ObsClass = BiasObservation if bias else DarkObservation
        observation = ObsClass(position=position)

        # Dark observations don't care if it's dark or not
        safety_kwargs = {"ignore": ["is_dark"]}

        # Most of the time we will take darks with the dome shut so can ignore weather safety
        with suppress(AttributeError):
            if self.dome.is_closed:
                self.logger.warning(f"Ignoring weather safety for {observation}.")
                safety_kwargs["ignore"].append("good_weather")

        # Take the observation (blocking)
        self.take_observation_block(observation, skip_focus=True, skip_slew=True,
                                    safety_kwargs=safety_kwargs, **kwargs)

    def assert_safe(self, *args, **kwargs):
        """ Raise a RuntimeError if not safe to continue.
        TODO: Raise a custom error type indicating lack of safety.
        Args:
            *args, **kwargs: Parsed to self._safety_func.
        """
        if self._safety_func is None:
            self.logger.warning("Safety function not set. Proceeding anyway.")

        elif not self._safety_func(*args, **kwargs):
            raise RuntimeError("Safety check failed!")

    def slew_to_observation(self, observation):
        """ Slew to the observation field coordinates. """
        self.logger.info(f"Slewing to target coordinates for {observation}.")

        if not self.mount.set_target_coordinates(observation.field.coord):
            raise RuntimeError(f"Unable to set target coordinates for {observation.field}.")

        self.mount.slew_to_target()

    # Private methods

    def _create_autoguider(self):
        guider_config = self.get_config('guider')
        guider = Guide(**guider_config)
        self.autoguider = guider

    def _move_all_filterwheels_to(self, filter_name, camera_names=None):
        """Move all the filterwheels to a given filter
        Args:
            filter_name (str): name of the filter where filterwheels will be moved to.
            camera_names (list, optional): List of camera names to be used.
                Default to `None`, which uses all cameras.
        """
        self.logger.debug(f'Moving all camera filterwheels to the {filter_name} filter.')

        if camera_names is None:
            cameras_list = self.cameras
        else:
            cameras_list = {c: self.cameras[c] for c in camera_names}

        # Move all the camera filterwheels to filter_name
        filterwheel_events = dict()
        for camera in cameras_list.values():
            filterwheel_events[camera] = camera.filterwheel.move_to(filter_name)

        # Wait for move to complete
        self.logger.debug(f'Waiting for all the filterwheels to move to the {filter_name} filter.')
        wait_for_events(list(filterwheel_events.values()))
        self.logger.debug('Finished waiting for filterwheels.')

    def _take_autoflats(self, cameras, observation, target_scaling=0.17, scaling_tolerance=0.05,
                        timeout=60, bias=32, remove_on_error=False, **kwargs):
        """ Take flat fields using automatic updates for exposure times.
        Args:
            cameras (dict): Dict of camera name: Camera pairs.
            observation: The flat field observation. TODO: Integrate with FlatFieldSequence.
            target_scaling (float, optional): Required to be between [0, 1] so
                target_adu is proportionally between 0 and digital saturation level.
                Default: 0.17.
            scaling_tolerance (float, optional): The minimum precision on the average counts
                required to keep the exposure, expressed as a fraction of the dynamic range.
                Default: 0.05.
            timeout (float): The timeout on top of the exposure time, default 60s.
            bias (int): The bias to subtract from the frames. TODO: Use a real bias image!
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
            **kwargs: Parsed to FlatFieldSequence.
        """
        cam_names = list(self.cameras.keys())

        # Create a flat field sequence for each camera
        sequences = {}
        for cam_name in cam_names:
            target_counts, counts_tolerance = self._autoflat_target_counts(
                cam_name, target_scaling, scaling_tolerance)
            sequences[cam_name] = FlatFieldSequence(
                target_counts=target_counts, counts_tolerance=counts_tolerance, bias=bias,
                **kwargs)

        # Loop until sequence has finished
        self.logger.info(f"Starting flat field sequence for {len(cam_names)} cameras.")
        while not all([s.is_finished for s in sequences.values()]):

            self.assert_safe(horizon="flat")

            # Slew to field
            self.slew_to_observation(observation)

            # Get standard fits headers
            headers = self.get_standard_headers(observation=observation)

            # Start the exposures on each camera
            events = {}
            exptimes = {}
            filenames = {}
            start_times = {}
            for cam_name, seq in sequences.items():
                camera = self.cameras[cam_name]

                # Get exposure time, filename and current time
                exptimes[cam_name] = seq.get_next_exptime(past_midnight=self.past_midnight)
                filenames[cam_name] = observation.get_exposure_filename(camera)
                start_times[cam_name] = current_time()

                # Start the exposure and get event
                # TODO: Replace with concurrent.futures
                try:
                    events[cam_name] = camera.take_observation(
                        observation, headers=headers, filename=filenames[cam_name],
                        exptime=exptimes[cam_name])
                except error.PanError as err:
                    self.logger.error(f"{err!r}")
                    self.logger.warning("Continuing with flat observation after error.")

            # Wait for the exposures
            self.logger.info('Waiting for flat field exposures to complete.')
            duration = get_quantity_value(max(exptimes.values()), u.second) + timeout
            try:
                self._wait_for_camera_events(events, duration, remove_on_error=remove_on_error,
                                             horizon="flat")
            except error.Timeout as err:
                self.logger.error(f"{err!r}")
                self.logger.warning("Continuing with flat observation after timeout error.")

            # Mark the current exposure as complete
            observation.mark_exposure_complete()

            # Update the flat field sequences with new data
            for cam_name in list(sequences.keys()):

                # Remove sequence for any removed cameras
                if cam_name not in self.cameras:
                    del sequences[cam_name]
                    continue

                # Attempt to update the exposure sequence for this camera.
                # If the exposure failed, use info from the last successful exposure.
                try:
                    sequences[cam_name].update(filename=filenames[cam_name],
                                               exptime=exptimes[cam_name],
                                               time_start=start_times[cam_name])
                except (KeyError, FileNotFoundError) as err:
                    self.logger.warning(f"Unable to update flat field sequence for {cam_name}:"
                                        f" {err!r}")
                # Log sequence status
                status = sequences[cam_name].status
                status["filter_name"] = observation.filter_name
                self.logger.info(f"Flat field status for {cam_name}: {status}")

            # Check if we need to terminate the sequence early
            if self.past_midnight:  # Sky getting brighter
                if all([s.is_too_bright and s.min_exptime_reached for s in sequences.values()]):
                    self.logger.info("Terminating flat field sequence for the "
                                     f"{observation.filter_name} filter because all exposures are"
                                     " too bright at the minimum exposure time.")
                    return
            else:  # Sky getting fainter
                if all([s.is_too_faint and s.max_exptime_reached for s in sequences.values()]):
                    self.logger.info("Terminating flat field sequence for the "
                                     f"{observation.filter_name} filter because all exposures are"
                                     " too faint at the maximum exposure time.")
                    return

    def _autoflat_target_counts(self, cam_name, target_scaling, scaling_tolerance):
        """ Get the target counts and tolerance for each camera.
        Args:
            cam_name (str): The camera name.
            target_scaling (float):
            scaling_tolerance (float):
        """
        camera = self.cameras[cam_name]
        try:
            bit_depth = camera.bit_depth.to_value(u.bit)
        except NotImplementedError:
            self.logger.debug(f'No bit_depth property for {cam_name}. Using 16.')
            bit_depth = 16

        target_counts = int(target_scaling * 2 ** bit_depth)
        counts_tolerance = int(scaling_tolerance * 2 ** bit_depth)

        self.logger.debug(f"Target counts for {cam_name}: {target_counts}"
                          f" ± {counts_tolerance}")
        return target_counts, counts_tolerance

    def _wait_for_camera_events(self, events, duration, remove_on_error=False, sleep=1, **kwargs):
        """ Wait for camera events to be set.
        Args:
            events (dict of camera_name: threading.Event): The events to wait for.
            duration (float): The total amount of time to wait for (should include exptime).
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
            sleep (float): Sleep this long between event checks. Default 1s.
            **kwargs: Parsed to self.assert_safe.
        """
        self.logger.debug(f'Waiting for {len(events)} events with timeout of {duration}.')

        timer = CountdownTimer(duration)
        while not timer.expired():

            # Check safety here
            self.assert_safe(**kwargs)

            # Check if all cameras have finished
            if all([e.is_set() for e in events.values()]):
                break
            time.sleep(sleep)

        # Make sure events are set
        for cam_name, event in events.items():
            if not event.is_set():
                if remove_on_error:
                    self.logger.warning(f"Timeout while waiting for camera event on {cam_name}. "
                                        "Removing from observatory.")
                    self.remove_camera(cam_name)
                else:
                    raise error.Timeout(f"Timeout while waiting for camera event on {cam_name}.")

    def _focus_required(self, coarse=False):
        """ Check if a focus is required based on current conditions.
        Args:
            coarse (bool): If True, check if we need to do a coarse focus. Default: False.
        Returns:
            bool: True if focus required, else False.
        """
        focus_type = "coarse" if coarse else "fine"

        # If a long time period has passed then focus again
        last_focus_time = getattr(self, f"last_{focus_type}_focus_time")
        interval = getattr(self, f"_{focus_type}_focus_interval")

        if last_focus_time is None:  # If we haven't focused yet
            return True
        if current_time() - last_focus_time > interval:
            self.logger.info(f"{focus_type} focus required because of time difference.")
            return True

        # If there has been a large change in temperature then we need to focus again
        last_focus_temp = getattr(self, f"last_{focus_type}_focus_temp")
        temptol = getattr(self, f"_{focus_type}_focus_temptol")

        if last_focus_temp and self.temperature:
            if abs(last_focus_temp - self.temperature) > temptol:
                self.logger.info(f"{focus_type} focus required because of temperature change.")
                return True

        return False
