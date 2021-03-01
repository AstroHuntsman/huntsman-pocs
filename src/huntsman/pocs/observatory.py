import os
import time
from contextlib import suppress
from functools import partial
from astropy import units as u

from panoptes.utils import error
from panoptes.utils.utils import altaz_to_radec, get_quantity_value
from panoptes.utils.library import load_module
from panoptes.utils.time import current_time, wait_for_events, CountdownTimer

from panoptes.pocs.observatory import Observatory
from panoptes.pocs.scheduler import constraint

from huntsman.pocs.guide.bisque import Guide
from panoptes.pocs.scheduler.observation.bias import BiasObservation
from huntsman.pocs.scheduler.observation.dark import DarkObservation
from huntsman.pocs.scheduler.observation.flat import FlatFieldObservation

from huntsman.pocs.archive.utils import remove_empty_directories
from huntsman.pocs.utils.flats import FlatFieldSequence


class HuntsmanObservatory(Observatory):

    def __init__(self,
                 with_autoguider=True,
                 hdr_mode=False,
                 take_flats=True,
                 *args, **kwargs
                 ):
        """Huntsman POCS Observatory

        Args:
            with_autoguider (bool, optional): If autoguider is attached, defaults to True.
            hdr_mode (bool, optional): If pics should be taken in HDR mode, defaults to False.
            take_flats (bool, optional): If flat field images should be taken, defaults to True.
            *args: Description
            **kwargs: Description
        """
        # Load the config file
        try:
            assert os.getenv('HUNTSMAN_POCS') is not None
        except AssertionError:
            raise RuntimeError("The HUNTSMAN_POCS environment variable is not set.")

        # If we don't receive a config then load a local
        super().__init__(*args, **kwargs)

        self._has_hdr_mode = hdr_mode
        self._has_autoguider = with_autoguider

        self.flat_fields_required = take_flats

        # Attributes for focusing
        self.last_focus_time = None
        self.coarse_focus_config = self.get_config('focusing.coarse')
        self._focus_frequency = self.coarse_focus_config['frequency'] \
            * u.Unit(self.coarse_focus_config['frequency_unit'])
        self._coarse_focus_filter = self.coarse_focus_config['filter_name']

        if self.has_autoguider:
            self.logger.info("Setting up autoguider")
            try:
                self._create_autoguider()
            except Exception as e:
                self._has_autoguider = False
                self.logger.warning(f"Problem setting autoguider, continuing without: {e!r}")

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
        """
        Return True if too much time has elapsed since the previous focus,
        using the amount of time specified by `focusing.coarse.frequency` in the config,
        else False.
        """
        if self.last_focus_time is None:
            return True
        if current_time() - self.last_focus_time > self._focus_frequency:
            return True
        return False

    @property
    def past_midnight(self):
        """Check if it's morning, useful for going into either morning or evening flats."""

        # Get the time of the nearest midnight to now
        midnight = self.observer.midnight(current_time(), which='nearest')

        # If the nearest midnight is in the past, it's the morning...
        return midnight < current_time()

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

    def autofocus_cameras(self, coarse=False, filter_name=None, *args, **kwargs):
        """ Override autofocus_cameras to update the last focus time and move filterwheels.
        Args:
            coarse (bool, optional): Perform coarse focus? Default False.
            filter_name (str, optional): The filter name to focus with. If None (default), will
                attempt to get from config, by default using the coarse focus filter.
            *args, **kwargs: Parsed to `pocs.observatory.Observatory.autofocus_cameras`.
        Returns:
            threading.Event: The autofocus event.
        """
        # Move to appropriate filter
        # TODO: Do this on a per-camera basis to allow for different filters simultaneously
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

        # Move all the filterwheels to the luminance position.
        self._move_all_filterwheels_to(filter_name)

        result = super().autofocus_cameras(coarse=coarse, *args, **kwargs)

        # Update last focus time
        self.last_focus_time = current_time()

        return result

    def cleanup_observations(self, *args, **kwargs):
        """ Override method to remove empty directories. Called in housekeeping state."""
        super().cleanup_observations(*args, **kwargs)

        self.logger.info("Removing empty directories in images directory.")
        images_dir = self.get_config("directories.images")
        remove_empty_directories(images_dir)

        self.logger.info("Removing empty directories in archive directory.")
        archive_dir = self.get_config("directories.archive")
        remove_empty_directories(archive_dir)

    def take_flat_fields(self, cameras=None, safety_func=None, **kwargs):
        """ Take flat fields for each camera in each filter, respecting filter order.
        Args:
            cameras (dict): Dict of cam_name: camera pairs. If None (default), use all cameras.
            safety_func (callable|None): Boolean function that returns True only if safe to
                continue. The default `None` will call `self.is_dark(horizon='flat')`.
            **kwargs: Overrides config entries under `calibs.flat`.
        """
        if cameras is None:
            cameras = self.cameras
        if safety_func is None:
            safety_func = partial(self.is_dark, horizon='flat')

        # Load the flat field config, allowing overrides from kwargs
        flat_config = self.get_config('calibs.flat', default=dict())
        flat_config.update(kwargs)

        # Specify flat field coordinates
        # This must be done at the observatory level to convert alt/az to ra/dec
        alt = flat_config['alt']
        az = flat_config['az']
        self.logger.debug(f'Flat field alt/az: {alt:.03f}, {az:.03f}.')

        # Specify filter order
        filter_order = flat_config['filter_order'].copy()
        if self.past_midnight:  # If it's the morning, order is reversed
            filter_order.reverse()

        # Take flat fields in each filter
        for filter_name in filter_order:
            if not safety_func():
                self.logger.info('Terminating flat-fielding because it is no longer safe.')
                return

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

            # Create the Observation object
            position = altaz_to_radec(alt=alt, az=az, location=self.earth_location,
                                      obstime=current_time())
            observation = FlatFieldObservation(position=position, filter_name=filter_name)
            observation.seq_time = current_time(flatten=True)

            # Take the flats for each camera in this filter
            self.logger.info(f'Taking flat fields in {filter_name} filter.')
            autoflat_config = flat_config.get("autoflats", {})
            self._take_autoflats(cameras_with_filter, observation, safety_func=safety_func,
                                 **autoflat_config)

        self.logger.info('Finished flat-fielding.')

    def take_bias_observation(self, cameras=None, **kwargs):
        """ Take a bias observation block on each camera (blocking).
        Args:
            cameras (dict, optional): Dict of cam_name: camera pairs. If None (default), use all
                the cameras.
        """
        if cameras is None:
            cameras = self.cameras
        # Create the observation
        position = self.mount.get_current_coordinates()
        observation = BiasObservation(position=position)
        # Take the observation (blocking)
        self._take_observation_block(observation, cameras=cameras, **kwargs)

    def take_dark_observation(self, exptimes=None, cameras=None, **kwargs):
        """ Take a dark observation block on each camera (blocking).
        Args:
            cameras (dict, optional): Dict of cam_name: camera pairs. If None (default), use all
                the cameras.
        """
        if cameras is None:
            cameras = self.cameras
        # Create the observation
        position = self.mount.get_current_coordinates()
        observation = DarkObservation(exptimes=exptimes, position=position)
        # Take the observation (blocking)
        self._take_observation_block(observation, cameras=cameras, **kwargs)

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

    def _take_observation_block(self, observation, cameras, timeout=60 * u.second,
                                remove_on_error=False):
        """ Take an observation block (blocking).
        Args:
            observation (Observation): The observation object.
            cameras (dict): Dict of cam_name: camera pairs. If None (default), use all cameras.
            timeout (float, optional): The timeout in addition to the exposure time. Default 60s.
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
        """
        observation.seq_time = current_time(flatten=True)  # Normally handled by the scheduler
        headers = self.get_standard_headers(observation=observation)
        # Take the observation block
        while not observation.set_is_finished:
            headers['start_time'] = current_time(flatten=True)  # Normally handled elsewhere?
            # Start the exposures and get events
            # TODO: Replace with concurrent.futures
            events = {}
            for cam_name, camera in cameras.items():
                try:
                    events[cam_name] = camera.take_observation(observation, headers=headers)
                except error.PanError as err:
                    self.logger.error(f"{err}!r")
                    self.logger.warning("Continuing with observation block after error on"
                                        f" {cam_name}.")
            # Wait for the exposures (blocking)
            # TODO: Use same timeout as camera client
            try:
                self._wait_for_camera_events(events, duration=observation.exptime + timeout,
                                             remove_on_error=remove_on_error)
            except error.Timeout as err:
                self.logger.error(f"{err!r}")
                self.logger.warning("Continuing with observation block after error.")

            # There's probably a better way of doing this but we've got bigger problems right now
            with suppress(AttributeError):
                observation.mark_exposure_complete()

    def _create_scheduler(self):
        """ Sets up the scheduler that will be used by the observatory """

        scheduler_config = self.get_config('scheduler', default=dict())
        scheduler_type = scheduler_config.get('type', 'dispatch')
        min_moon_sep = scheduler_config.get('min_moon_sep', 45)

        # Read the targets from the file
        fields_file = scheduler_config.get('fields_file', 'simple.yaml')
        fields_path = os.path.join(self.get_config('directories.targets'), fields_file)

        self.logger.debug(f'Creating scheduler: {fields_path}')

        if os.path.exists(fields_path):

            try:
                # Load the required module
                module = load_module(f'huntsman.scheduler.{scheduler_type}')

                # Simple constraint for now
                constraints = [
                    constraint.MoonAvoidance(),
                    constraint.Duration(30 * u.deg)]

                # Create the Scheduler instance
                self.scheduler = module.Scheduler(
                    self.observer, fields_file=fields_path, constraints=constraints)
                self.scheduler.common_properties['min_moon_sep'] = min_moon_sep
                self.logger.debug("Scheduler created")
            except ImportError as e:
                raise error.NotFound(msg=e)
        else:
            raise error.NotFound(msg=f"Fields file does not exist: {fields_file}")

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
        self.logger.debug(f'Finished waiting for filterwheels.')

    def _take_autoflats(self, cameras, observation, target_scaling=0.17, scaling_tolerance=0.05,
                        timeout=60, bias=32, safety_func=None, remove_on_error=False, **kwargs):
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
            safety_func (None or callable): If given, calls to this object return True if safe to
                continue.
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

            if not safety_func():
                self.logger.warning("Terminating flat fields because safety check failed.")
                return

            # Slew to field
            self.logger.info(f'Slewing to flat field coordinates: {observation.field}.')
            self.mount.set_target_coordinates(observation.field)
            self.mount.slew_to_target()

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
                    self.logger.error(f"{err}!r")
                    self.logger.warning("Continuing with flat observation after error.")

            # Wait for the exposures
            self.logger.info('Waiting for flat field exposures to complete.')
            duration = get_quantity_value(max(exptimes.values()), u.second) + timeout
            try:
                self._wait_for_camera_events(events, duration, remove_on_error=remove_on_error)
            except error.Timeout as err:
                self.logger.error(f"{err}!r")
                self.logger.warning("Continuing with flat observation after timeout error.")

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
                                        f" {err}!r")
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

    def _wait_for_camera_events(self, events, duration, remove_on_error=False, sleep=1):
        """ Wait for camera events to be set.
        Args:
            events (dict of camera_name: threading.Event): The events to wait for.
            duration (float): The total amount of time to wait for (should include exptime).
            remove_on_error (bool, default False): If True, remove cameras that timeout. If False,
                raise a TimeoutError instead.
            sleep (float): Sleep this long between event checks. Default 1s.
        """
        self.logger.debug(f'Waiting for {len(events)} events with timeout of {duration}.')
        timer = CountdownTimer(duration)
        while not timer.expired():
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
