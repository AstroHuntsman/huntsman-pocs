import time
from contextlib import suppress, contextmanager
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
from huntsman.pocs.utils.flats import make_flat_field_sequences, make_flat_field_observation
from huntsman.pocs.utils.flats import get_cameras_with_filter
from huntsman.pocs.utils.safety import get_solar_altaz
from huntsman.pocs.camera.group import CameraGroup, dispatch_parallel
from huntsman.pocs.error import NotTwilightError, NotSafeError


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
        super().__init__(logger=logger, *args, **kwargs)

        # Make a camera group
        self.camera_group = CameraGroup(self.cameras)

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
        self._is_safe = None

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
    def is_past_midnight(self):
        """Check if it's morning, useful for going into either morning or evening flats."""
        # Get the time of the nearest midnight to now
        # If the nearest midnight is in the past, it's the morning
        midnight = self.observer.midnight(current_time(), which='nearest')
        return midnight < current_time()

    @property
    def is_twilight(self):
        """ Return True if it is twilight, else False. """
        return self.is_dark(horizon="twilight_max") and not self.is_dark(horizon="twilight_min")

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

    @property
    def solar_altaz(self):
        """ Return the current solar alt az. """
        return get_solar_altaz(location=self.earth_location, time=current_time())

    # Context managers

    @contextmanager
    def safety_checking(self, *args, **kwargs):
        """ Check safety before and after the code block.
        To be used with a "with" statement, e.g.:
            with self.safety_checking():
                print(x)
        Args:
            *args, **kwargs: Parsed to self._assert_safe
        Raises:
            NotSafeError: If not safe.
        """
        self._assert_safe(*args, **kwargs)
        try:
            yield None
        finally:
            self._assert_safe(*args, **kwargs)

    # Methods

    def initialize(self):
        """Initialize the observatory and connected hardware """
        super().initialize()

        if self.has_autoguider:
            self.logger.debug("Connecting to autoguider")
            self.autoguider.connect()

    def is_safe(self, park_if_not_safe=False, *args, **kwargs):
        """ Return True if it is safe, else False.
        Args:
            *args, **kwargs: Parsed to self._is_safe. See panoptes.pocs.core.POCS.is_safe.
            park_if_not_safe (bool): If True, park if safety fails. Default: False.
        Returns:
            bool: True if safe, else False.
        """
        if self._is_safe is not None:
            return self._is_safe(park_if_not_safe=park_if_not_safe, *args, **kwargs)
        self.logger.warning("Safety function not set. Returning False")
        return False

    def remove_camera(self, cam_name):
        """ Remove a camera from the observatory.
        Args:
            cam_name (str): The name of the camera to remove.
        """
        super().remove_camera(cam_name)
        with suppress(KeyError):
            del self.camera_group.cameras[cam_name]

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

        # Asyncronously dispatch autofocus calls
        with self.safety_checking(horizon="focus"):
            events = self.camera_group.autofocus(coarse=coarse, filter_name=filter_name, **kwargs)

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
        if self.is_past_midnight:  # If it's the morning, order is reversed
            filter_order.reverse()

        # Take flat fields in each filter
        for filter_name in filter_order:

            # Check if it is appropriate to continue with flats
            if not self.is_twilight:
                raise NotTwilightError("No longer twilight. Aborting flat fields.")

            if not self.is_safe(horizon="twilight_max"):
                raise NotSafeError("Not safe to continue with flat fields. Aborting.")

            # Get a dict of cameras that have this filter
            cameras_with_filter = get_cameras_with_filter(cameras, filter_name)

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

    def prepare_cameras(self, drop=True, *args, **kwargs):
        """ Make sure cameras are all cooled and ready.
        Args:
            drop (bool): If True, drop cameras that do not become ready in time. Default: True.
            *args, **kwargs: Parsed to self.camera_group.wait_until_ready.
        """
        self.logger.info(f"Preparing {len(self.cameras)} cameras.")

        failed_cameras = self.camera_group.wait_until_ready(*args, **kwargs)

        # Remove cameras that didn't become ready in time
        if drop:
            for cam_name in failed_cameras:
                self.logger.debug(f'Removing {cam_name} from {self} for not being ready.')
                self.remove_camera(cam_name)

    def take_observation_block(self, observation, cameras=None, timeout=60 * u.second,
                               remove_on_error=False, do_focus=True, safety_kwargs=None,
                               do_slew=True):
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
            do_slew (bool, optional): If True, do not attempt to slew the telescope. Default
                False.
            **safety_kwargs (dict, optional): Extra kwargs to be parsed to safety function.
        Raises:
            NotSafeError: If safety check fails.
        """
        if cameras is None:
            cameras = self.cameras

        safety_kwargs = {} if safety_kwargs is None else safety_kwargs
        self._assert_safe(**safety_kwargs)

        # Set the sequence time of the observation
        if observation.seq_time is None:
            observation.seq_time = current_time(flatten=True)

        headers = self.get_standard_headers(observation=observation)

        # Take the observation block
        self.logger.info(f"Starting observation block for {observation}")

        # The start new set flag is True before we enter the loop and is set to False
        # immediately inside the loop. This allows the loop to start a new set in case
        # the set_is_finished condition is already satisfied.
        start_new_set = True

        current_field = None
        while (start_new_set or not observation.set_is_finished):

            start_new_set = False  # We don't want to start another set after this one

            # Perform the slew if necessary
            slew_required = (current_field != observation.field) and do_slew
            if slew_required:
                with self.safety_checking(**safety_kwargs):
                    self.slew_to_observation(observation)
                current_field = observation.field

            # Fine focus the cameras if necessary
            focus_required = self.fine_focus_required or observation.current_exp_num == 0
            if do_focus and focus_required:
                with self.safety_checking(**safety_kwargs):
                    self.autofocus_cameras(blocking=True, filter_name=observation.filter_name)

            # Set a common start time for this batch of exposures
            headers['start_time'] = current_time(flatten=True)

            # Start the exposures and get events
            with self.safety_checking(**safety_kwargs):
                events = self.camera_group.take_observation(observation, headers=headers)

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

            self.logger.info(f"Observation status: {observation.status}")

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

        # Can ignore weather safety if dome is closed
        with suppress(AttributeError):
            if self.dome.is_closed:
                self.logger.warning(f"Ignoring weather safety for {observation}.")
                safety_kwargs["ignore"].append("good_weather")

        # Take the observation (blocking)
        self.take_observation_block(observation, do_focus=False, do_slew=False,
                                    safety_kwargs=safety_kwargs, **kwargs)

    def slew_to_observation(self, observation, min_solar_alt=10 * u.deg):
        """ Slew to the observation field coordinates.
        Args:
            observation (Observation): The observation object.
            min_solar_alt (astropy.Quantity, optional): The minimum solar altitude above which the
                FWs will be moved to their dark positions before slewing.
        """
        self.logger.info(f"Slewing to target coordinates for {observation}.")

        if not self.mount.set_target_coordinates(observation.field.coord):
            raise RuntimeError(f"Unable to set target coordinates for {observation.field}.")

        # Move FWs to dark pos if Sun too high to minimise damage potential
        move_fws = self.solar_altaz.alt > get_quantity_value(min_solar_alt, u.deg) * u.deg

        if move_fws:
            self.logger.warning("Solar altitude above minimum for safe slew. Moving FWs to dark"
                                " positions.")

            # Record curent positions so we can put them back after slew
            # NOTE: These positions could include the dark position so can't use last_light_position
            current_fw_positions = {}
            for cam_name, cam in self.cameras.items():
                if cam.has_filterwheel:
                    current_fw_positions[cam_name] = cam.filterwheel.current_filter

            self.camera_group.filterwheel_move_to(current_fw_positions)

        self.mount.slew_to_target()

        if move_fws:
            self.logger.info("Moving FWs back to last positions.")
            self.camera_group.filterwheel_move_to(current_fw_positions)

    # Private methods

    def _create_autoguider(self):
        guider_config = self.get_config('guider')
        guider = Guide(**guider_config)
        self.autoguider = guider

    def _take_autoflats(
            self, cameras, observation, target_scaling=0.17, scaling_tolerance=0.05, timeout=60,
            bias=32, remove_on_error=False, sleep_time=300, evening_initial_flat_exptime=0.01,
            morning_initial_flat_exptime=1, **kwargs):
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
        # set the initial exposure time
        if self.is_past_midnight:
            initial_exptime = morning_initial_flat_exptime
        else:
            initial_exptime = evening_initial_flat_exptime

        # Create a flat field sequence for each camera
        sequences = make_flat_field_sequences(cameras, target_scaling, scaling_tolerance,
                                              bias, initial_exposure_time=initial_exptime, **kwargs)

        # Loop until sequence has finished
        self.logger.info(f"Starting flat field sequence for {len(self.cameras)} cameras.")
        while True:

            if not self.is_twilight:
                raise NotTwilightError("No longer twilight. Aborting flat fields.")

            # Slew to field
            with self.safety_checking(horizon="twilight_max"):
                self.slew_to_observation(observation)

            # Get standard fits headers
            headers = self.get_standard_headers(observation=observation)

            events = {}
            exptimes = {}
            filenames = {}
            start_times = {}

            # Define function to start the exposures
            def func(cam_name):
                seq = sequences[cam_name]
                camera = cameras[cam_name]

                # Get exposure time, filename and current time
                exptimes[cam_name] = seq.get_next_exptime(past_midnight=self.is_past_midnight)
                filenames[cam_name] = observation.get_exposure_filename(camera)
                start_times[cam_name] = current_time()

                try:
                    events[cam_name] = camera.take_observation(
                        observation, headers=headers, filename=filenames[cam_name],
                        exptime=exptimes[cam_name])
                except error.PanError as err:
                    self.logger.error(f"{err!r}")
                    self.logger.warning("Continuing with flat observation after error.")

            # Start the exposures in parallel
            dispatch_parallel(func, list(cameras.keys()))

            # Wait for the exposures
            self.logger.info('Waiting for flat field exposures to complete.')
            duration = get_quantity_value(max(exptimes.values()), u.second) + timeout
            try:
                self._wait_for_camera_events(events, duration, remove_on_error=remove_on_error,
                                             horizon="twilight_max")
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

            # Check if sequences are complete
            if all([s.is_finished for s in sequences.values()]):
                self.logger.info("All flat field sequences finished.")
                break

            # Check if counts are ok
            if self.is_past_midnight:

                # Terminate if Sun is coming up and all exposures are too bright
                if all([s.min_exptime_reached for s in sequences.values()]):
                    self.logger.info(f"Terminating flat sequence for {observation.filter_name}"
                                     f" filter because min exposure time reached.")
                    break

                # Wait if Sun is coming up and all exposures are too faint
                elif all([s.max_exptime_reached for s in sequences.values()]):
                    self.logger.info(f"All exposures are too faint. Waiting for {sleep_time}s")
                    self._safe_sleep(sleep_time, horizon="twilight_max")

            else:
                # Terminate if Sun is going down and all exposures are too faint
                if all([s.max_exptime_reached for s in sequences.values()]):
                    self.logger.info(f"Terminating flat sequence for {observation.filter_name}"
                                     f" filter because max exposure time reached.")
                    break

                # Wait if Sun is going down and all exposures are too bright
                elif all([s.max_exptime_reached for s in sequences.values()]):
                    self.logger.info(f"All exposures are too bright. Waiting for {sleep_time}s")
                    self._safe_sleep(sleep_time, horizon="twilight_max")

    def _wait_for_camera_events(self, events, duration, remove_on_error=False, sleep=1, **kwargs):
        """ Wait for camera events to be set.
        Args:
            events (dict of camera_name: threading.Event): The events to wait for.
            duration (float): The total amount of time to wait for (should include exptime).
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
            sleep (float): Sleep this long between event checks. Default 1s.
            **kwargs: Parsed to self._assert_safe.
        """
        self.logger.debug(f'Waiting for {len(events)} events with timeout of {duration}.')

        timer = CountdownTimer(duration)
        while not timer.expired():

            # Check safety here
            self._assert_safe(**kwargs)

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
            self.logger.info(f"{focus_type} focus required because we haven't focused yet.")
            return True

        if current_time() - last_focus_time > interval:
            self.logger.info(f"{focus_type} focus required because of time difference.")
            return True

        # If there has been a large change in temperature then we need to focus again
        last_focus_temp = getattr(self, f"last_{focus_type}_focus_temp")
        temptol = getattr(self, f"_{focus_type}_focus_temptol")

        if (last_focus_temp is not None) and (self.temperature is not None):
            if abs(last_focus_temp - self.temperature) > temptol:
                self.logger.info(f"{focus_type} focus required because of temperature change.")
                return True

        return False

    def _assert_safe(self, *args, **kwargs):
        """ Raise a NotSafeError if not safe to continue.
        TODO: Raise a custom error type indicating lack of safety.
        Args:
            *args, **kwargs: Parsed to self.is_safe.
        """
        if not self.is_safe(*args, **kwargs):
            raise NotSafeError("Safety check failed!")

    def _safe_sleep(self, duration, interval=1, *args, **kwargs):
        """ Sleep for a specified amount of time while ensuring safety.
        A NotSafeError is raised if safety fails while waiting.
        Args:
            duration (float or Quantity): The time to wait.
            interval (float): The time in between safety checks.
            *args, **kwargs: Parsed to is_safe.
        Raises:
            NotSafeError: If safety fails while waiting.
        """
        self.logger.debug(f"Safe sleeping for {duration}")
        timer = CountdownTimer(duration)
        while not timer.expired():
            self._assert_safe(*args, **kwargs)
            time.sleep(interval)
