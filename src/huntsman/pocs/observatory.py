import os
import time
from collections import defaultdict
from contextlib import suppress
from functools import partial

from astropy import stats
from astropy import units as u
from astropy.io import fits

from panoptes.utils import error, altaz_to_radec, listify, get_quantity_value
from panoptes.utils.library import load_module
from panoptes.utils.time import current_time, flatten_time, wait_for_events

from panoptes.pocs.observatory import Observatory
from panoptes.pocs.scheduler import constraint

from huntsman.pocs.guide.bisque import Guide
from huntsman.pocs.scheduler.dark_observation import DarkObservation
from huntsman.pocs.scheduler.observation import DitheredFlatObservation
from huntsman.pocs.archive.utils import remove_empty_directories


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

    def autofocus_cameras(self, coarse=False, *args, **kwargs):
        """ Override autofocus_cameras to update the last focus time and move filterwheels.
        Args:
            coarse (bool, optional): Perform coarse focus? Default False.
            *args, **kwargs: Parsed to `pocs.observatory.Observatory.autofocus_cameras`.
        Returns:
            threading.Event: The autofocus event.
        """
        # Move to appropriate filter
        # TODO: Do this on a per-camera basis to allow for different filters simultaneously
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

    def take_flat_fields(self, camera_names=None, alt=None, az=None, safety_func=None, **kwargs):
        """
        Take flat fields for each camera in each filter, respecting filter order.

        Args:
            camera_names (list, optional): List of camera names to take flats with.
                Default to `None`, which uses all cameras.
            alt (float, optional): Altitude for flats in degrees. Default `None` will use the
                `flat_fields.alt` config value.
            az (float, optional): Azimuth for flats in degrees. Default `None` will use the
                `flat_fields.az` config value.
            bias (int, optional): Default bias in ADU counts for the cameras. Default 32.
            target_scaling (float, optional): Required to be between [0,1] so
                target_adu is proportionally between 0 and digital saturation level.
                Default 0.17.
            tolerance (float, optional): The minimum precision on the average counts required to
                keep the exposure, expressed as a fraction of the dynamic range. Default 0.1.
            required_exposures (int, optional): Maximum number of good flat-fields to
                take per filter. Default 10.
            max_attempts (int, optional): Number of attempts per camera-filter pair to get good
                flat-field exposures before aborting. Default 20.
            safety_func (callable|None): Boolean function that returns True only if safe to
                continue. The default `None` will call `self.is_dark(horizon='flat')`.
        """
        if safety_func is None:
            safety_func = partial(self.is_dark, horizon='flat')

        # Load the flat fielding config
        flat_field_config = self.get_config('flat_fields', default=dict())
        flat_field_config.update(kwargs)

        # Specify flat field coordinates
        if (alt is None) or (az is None):
            self.logger.debug(f'Using flat-field alt/az from config.')
            alt = flat_field_config['alt']
            az = flat_field_config['az']

        if camera_names is None:
            cameras_all = self.cameras
        else:
            cameras_all = {c: self.cameras[c] for c in camera_names}

        # Obtain the filter order
        filter_order = flat_field_config['filter_order'].copy()
        if self.past_midnight:  # If it's the morning, order is reversed
            filter_order.reverse()

        exptimes_dark = defaultdict(set)
        for filter_name in filter_order:

            if not safety_func():
                self.logger.info('Terminating flat-fielding because it is no longer safe.')
                return

            # Get a dict of cameras that have this filter
            filter_cameras = {}
            for cam_name, cam in cameras_all.items():
                if cam.filterwheel is None:
                    if cam.filter_type == filter_name:
                        filter_cameras[cam_name] = cam
                elif filter_name in cam.filterwheel.filter_names:
                    filter_cameras[cam_name] = cam

            # Go to next filter if there are no cameras with this one
            if not filter_cameras:
                self.logger.debug(f'No cameras found with {filter_name} filter.')
                continue

            # Create the Observation object
            obs = self._create_flat_field_observation(alt=alt, az=az, filter_name=filter_name)

            # Take the flats for each camera in this filter
            self.logger.info(f'Taking flat fields in {filter_name} filter.')
            exptimes = self._take_autoflats(filter_cameras, obs, safety_func=safety_func,
                                            **flat_field_config)

            # Log the new exposure times we need to take darks with
            for cam_name in filter_cameras.keys():
                exptimes_dark[cam_name].update(exptimes[cam_name])

        # Take darks for each exposure time we used
        self.logger.info('Taking flat field dark frames.')
        obs = self._create_flat_field_observation(alt=alt, az=az)
        for exptime in exptimes_dark:
            self._take_flat_field_darks(exptimes_dark, obs, safety_func, **flat_field_config)

        self.logger.info('Finished flat-fielding.')

    def take_dark_images(self, exptimes=None, camera_names=None, n_darks=10, imtype='dark',
                         set_from_config=False, *args, **kwargs):
        """Take n_darks for each exposure time specified,
           for each camera.

        Args:
            exptimes (list, optional): List of exposure times for darks
            camera_names (list, optional): List of cameras to use for darks
            n_darks (int or list, optional): if int, the same number of darks will be taken
                for each exptime. If list, the len has to be the same than len(exptimes), where each
                element is the number of darks we want for the corresponding exptime, e.g.:
                take_dark_images(exptimes=[1*u.s, 60*u.s, 15*u.s], n_darks=[30, 10, 20])
                will take 30x1s, 10x60s, and 20x15s darks
            set_from_config (bool, optional): flag to set exptimes and n_darks directly
                from config file.
            imtype (str, optional): type of image
        """

        if exptimes is None:
            exptimes = list()

        if camera_names is None:
            cameras_list = self.cameras
        else:
            cameras_list = {c: self.cameras[c] for c in camera_names}

        self.logger.debug(f'Using cameras {cameras_list}')

        # Move all the filterwheels to the blank position.
        self._move_all_filterwheels_to('blank')

        # List to check that the final number of darks is equal to the number
        # of cameras times the number of exptimes times n_darks.
        darks_filenames = list()

        exptimes = listify(exptimes)

        if set_from_config:
            dark_config = self.get_config('darks', default=dict())
            exptimes = dark_config['exposure_time']
            n_darks = dark_config['n_darks']

        if not isinstance(n_darks, list):
            n_darks = listify(n_darks) * len(exptimes)

        # Loop over cameras.
        if len(exptimes) == 0:
            raise error.PanError('No exposure times were provided. No dark images were taken.')

        self.logger.info(f'Going to take {n_darks} darks for these exposure times {exptimes}')
        for exptime, num_darks in zip(exptimes, n_darks):

            start_time = current_time()

            with suppress(AttributeError):
                exptime = get_quantity_value(exptime, u.second)

            # Create dark observation
            dark_obs = self._create_dark_observation(exptime)

            # Loop over exposure times for each camera.
            for num in range(num_darks):

                self.logger.debug(f'Taking dark {num + 1} of {num_darks} with exptime={exptime} s.')

                camera_events = dict()

                # Take a given number of exposures for each exposure time.
                for camera in cameras_list.values():

                    # Set header
                    fits_headers = self.get_standard_headers(observation=dark_obs)
                    # Common start time for cameras
                    fits_headers['start_time'] = flatten_time(start_time)

                    # Create filename
                    path = os.path.join(dark_obs.directory, camera.uid, dark_obs.seq_time)

                    filename = os.path.join(path, f'{imtype}_{num:02d}.{camera.file_extension}')

                    # Take picture and get event
                    camera_event = camera.take_observation(
                        dark_obs,
                        fits_headers,
                        filename=filename,
                        exptime=exptime,
                        dark=True,
                        blocking=False
                    )

                    self.logger.debug(f'Camera {camera.uid} is exposing for {exptime}s')

                    camera_events[camera] = {
                        'event': camera_event,
                        'filename': filename,
                    }

                    darks_filenames.append(filename)

                    self.logger.debug(camera_events)

                # Block until done exposing on all cameras
                self.logger.debug('Waiting for dark images...')
                wait_for_events(list(info['event'] for info in camera_events.values()))
        self.logger.debug(darks_filenames)
        return darks_filenames

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

    def _create_scheduler(self):
        """ Sets up the scheduler that will be used by the observatory """

        scheduler_config = self.get_config('scheduler', default=dict())
        scheduler_type = scheduler_config.get('type', 'dispatch')

        # Read the targets from the file
        fields_file = scheduler_config.get('fields_file', 'simple.yaml')
        fields_path = os.path.join(self.get_config('directories.targets'), fields_file)

        self.logger.debug(f'Creating scheduler: {fields_path}')

        if os.path.exists(fields_path):

            try:
                # Load the required module
                module = load_module(f'huntsman.scheduler.{scheduler_type}')

                # Simple constraint for now
                constraints = [constraint.MoonAvoidance(), constraint.Duration(30 * u.deg)]

                # Create the Scheduler instance
                self.scheduler = module.Scheduler(
                    self.observer, fields_file=fields_path, constraints=constraints)
                self.logger.debug("Scheduler created")
            except ImportError as e:
                raise error.NotFound(msg=e)
        else:
            raise error.NotFound(msg=f"Fields file does not exist: {fields_file}")

    def _create_autoguider(self):
        guider_config = self.get_config('guider')
        guider = Guide(**guider_config)

        self.autoguider = guider

    def _create_flat_field_observation(self, alt, az, *args, **kwargs):
        """Create the flat-field `Observation` object."""
        flat_coords = altaz_to_radec(alt=alt, az=az, location=self.earth_location,
                                     obstime=current_time())
        self.logger.debug(f'Making flat-field observation for alt/az: {alt:.03f}, {az:.03f}.')
        self.logger.debug(f'Flat field coordinates: {flat_coords}')

        # Create the Observation object
        obs = DitheredFlatObservation(position=flat_coords, *args, **kwargs)
        obs.seq_time = current_time(flatten=True)
        self.logger.debug(f"Created flat-field observation: {obs}")

        return obs

    def _create_dark_observation(self, exptime, *args, **kwargs):

        # Create the observation object
        dark_position = self.mount.get_current_coordinates()
        dark_obs = DarkObservation(dark_position, *args, **kwargs)
        dark_obs.seq_time = current_time(flatten=True)

        if isinstance(dark_obs, DarkObservation):
            dark_obs.exptime = exptime

        return dark_obs

    def _take_autoflats(self, cameras, observation, safety_func, tolerance=0.05,
                        target_scaling=0.17, bias=32, min_exptime=1 * u.second,
                        max_exptime=60 * u.second, required_exposures=10, max_attempts=20,
                        *args, **kwargs):
        """Take flat fields iteratively by automatically estimating exposure times.

        Args:
            cameras (dict): Dict of camera name: Camera pairs.
            filter_names (dict): Dict of filter name for each camera.
            safety_func (func): Boolean function that returns True only if safe to continue.
        """
        # Get the target counts and tolerance for each camera
        target_counts = {}
        counts_tolerance = {}
        for cam_name, cam in cameras.items():
            try:
                bit_depth = cam.bit_depth.to_value(u.bit)
            except NotImplementedError:
                self.logger.debug(f'No bit_depth property for {cam_name}. Using 16.')
                bit_depth = 16
            target_counts[cam_name] = target_scaling * 2 ** bit_depth
            counts_tolerance[cam_name] = tolerance * 2 ** bit_depth
            self.logger.debug(f'Target counts for {cam_name}: '
                              f'{target_counts[cam_name]}±{counts_tolerance[cam_name]}.')

        # Setup containers with initial values
        exptimes = {cam_name: [1. * u.second] for cam_name in cameras.keys()}
        finished = {cam_name: False for cam_name in cameras.keys()}
        n_good_exposures = {cam_name: 0 for cam_name in cameras.keys()}

        # Loop until conditions are met to finish flat-fielding
        for attempt_number in range(max_attempts):

            if all(finished.values()):
                self.logger.info(f'All cameras have finished flat-fielding in'
                                 f' {observation.filter_name} filter.')
                break

            if not safety_func():
                self.logger.info('Stopping flat-fielding as no longer safe.')
                break

            # Get the FITS headers with a common start time
            start_time = current_time()
            fits_headers = self.get_standard_headers(observation=observation)
            fits_headers['start_time'] = flatten_time(start_time)

            # Take the flat field observations (blocking)
            current_exptimes = {c: exptimes[c][-1] for c in cameras.keys() if not finished[c]}
            # Only cameras with successful exposures are kept in camera_events
            camera_events = self._take_flat_observation(current_exptimes, observation,
                                                        fits_headers=fits_headers, **kwargs)

            # Check whether each camera has finished
            all_too_bright = True
            all_too_faint = True
            for cam_name, meta in camera_events.items():
                current_exptime = current_exptimes[cam_name]

                # Calculate mean counts of last image
                mean_counts = self._autoflat_mean_counts(meta['filename'], bias)
                self.logger.debug(f'Mean flat-field counts for {cam_name} following'
                                  f' {current_exptime} exposure: {mean_counts:.0f}.'
                                  f' Target counts: {target_counts[cam_name]:.0f}.')

                # Check if the current exposure is good enough to keep
                max_counts = target_counts[cam_name] + counts_tolerance[cam_name]
                min_counts = target_counts[cam_name] - counts_tolerance[cam_name]
                self.logger.debug(f'Valid flat-field counts range for {cam_name}: '
                                  f'{min_counts:.0f}, {max_counts:.0f}.')

                is_too_bright = mean_counts > max_counts
                is_too_faint = mean_counts < min_counts
                all_too_bright &= is_too_bright
                all_too_faint &= is_too_faint
                if is_too_bright:
                    self.logger.debug(f'Counts too high for flat-field'
                                      f' image on {cam_name}: {mean_counts:.0f}>{max_counts:.0f}.')
                elif is_too_faint:
                    self.logger.debug(f'Counts too low for flat-field'
                                      f' image on {cam_name}: {mean_counts:.0f}<{min_counts:.0f}.')
                    # TODO Mark low counts somehow.
                else:
                    n_good_exposures[cam_name] += 1
                self.logger.debug(f'Current acceptable flat-field exposures for {cam_name} '
                                  f'in {observation.filter_name} filter after {attempt_number + 1} '
                                  f'attempts: {n_good_exposures[cam_name]} of {required_exposures}.')

                # Check if we have enough good flats for this camera
                if n_good_exposures[cam_name] >= required_exposures:
                    self.logger.debug('Enough acceptable flat-field exposures acquired for '
                                      f'{cam_name} in {observation.filter_name} filter.')
                    finished[cam_name] = True
                    continue

                # Calculate next exposure time
                elapsed_time = (current_time() - start_time).sec
                next_exptime = self._autoflat_next_exptime(
                    current_exptime, elapsed_time, target_counts[cam_name], mean_counts)
                self.logger.debug('Suggested flat-field exposure time for '
                                  f'{cam_name}: {next_exptime}.')

                # Check the next exposure time is within limits
                if next_exptime >= max_exptime:
                    self.logger.debug(f'Suggested flat-field exposure time for {cam_name}'
                                      f' is too long: {next_exptime}.')
                    if not self.past_midnight:
                        finished[cam_name] = True  # It's getting darker, so finish
                        self.logger.debug('Premature termination of flat-field exposures for '
                                          f'{cam_name} in {observation.filter_name}.')
                        continue
                    next_exptime = max_exptime
                elif next_exptime < min_exptime:
                    self.logger.debug(f'Suggested flat-field exposure time for {cam_name}'
                                      f' is too short: {next_exptime}.')
                    if self.past_midnight:
                        finished[cam_name] = True  # It's getting lighter, so finish
                        self.logger.debug('Premature termination of flat-field exposures for '
                                          f'{cam_name} in {observation.filter_name}.')
                        continue
                    next_exptime = min_exptime

                # Update the next exposure time
                exptimes[cam_name].append(next_exptime)

            # Check if all the exposures in this loop are too bright
            if self.past_midnight:
                if all_too_faint:
                    self.logger.debug('All flat-field exposures are too faint. '
                                      'Waiting 30 seconds...')
                    time.sleep(30)
            else:
                if all_too_bright:
                    self.logger.debug('All flat-field exposures are too bright. '
                                      'Waiting 30 seconds...')
                    time.sleep(30)

            if attempt_number == max_attempts - 1:
                self.logger.debug('Max attempts have been reached for flat-fielding '
                                  f'in {observation.filter_name} filter. Aborting.')

        # Return the exposure times
        return exptimes

    def _autoflat_mean_counts(self, filename, bias, min_counts=1):
        """ Read the data and calculate a clipped-mean count rate.

        Args:
            filename (str): The filename containing the data.
            bias (float): The bias level to subtract from the image.
            min_counts (float): The minimum count rate returned by this funtion.
        """
        try:
            data = fits.getdata(filename)
        except FileNotFoundError:
            data = fits.getdata(filename + '.fz')
        data = data.astype('int32')

        # Calculate average counts per pixel
        mean_counts, _, _ = stats.sigma_clipped_stats(data - bias)
        if mean_counts < min_counts:
            self.logger.warning('Truncating mean flat-field counts to minimum value: '
                                f'{mean_counts}<{min_counts}.')
            mean_counts = min_counts

        return mean_counts

    def _autoflat_next_exptime(self, previous_exptime, elapsed_time, target_counts, mean_counts):
        """Calculate the next exposure time for the flat fields, accounting
        for changes in sky brightness."""
        exptime = previous_exptime * (target_counts / mean_counts)
        sky_factor = 2.0 ** (elapsed_time / 180.0)
        if self.past_midnight:
            exptime = exptime / sky_factor
        else:
            exptime = exptime * sky_factor
        return exptime.to_value(u.second) * u.second

    def _take_flat_observation(self, exptimes, observation, fits_headers=None, dark=False,
                               timeout=120, **kwargs):
        """
        Slew to flat field, take exposures and wait for them to complete.
        Returns a list of camera events for each camera.

        args:
            exptimes: dict of camera_name: list of exposure times.
            observation: Flat field Observation object.
        """
        imtype = 'dark' if dark else 'flat'
        if fits_headers is None:
            fits_headers = self.get_standard_headers(observation=observation)

        # Slew to field
        self.logger.debug(f'Slewing to flat-field coords: {observation.field}.')
        self.mount.set_target_coordinates(observation.field)
        self.mount.slew_to_target()

        # Loop over cameras...
        camera_events = {}
        for cam_name, exptime in exptimes.items():
            cam = self.cameras[cam_name]

            # Create filename
            path = os.path.join(observation.directory, cam.uid, observation.seq_time)
            filename = os.path.join(
                path, f'{imtype}_{observation.current_exp_num:02d}.{cam.file_extension}')

            # Take exposure and get event
            exptime = exptime.to_value(u.second)
            camera_event = cam.take_observation(observation, fits_headers, filename=filename,
                                                exptime=exptime, dark=dark)
            camera_events[cam_name] = {'event': camera_event, 'filename': filename}

        # Block until done exposing on all cameras
        exposure_timeout = max(exptimes.values()).to_value(u.second) + timeout
        self.logger.debug(f"Waiting for flat-fields with timeout of {exposure_timeout}.")
        if not wait_for_events([c["event"] for c in camera_events.values()],
                               timeout=exposure_timeout, sleep_delay=1):
            self.logger.error("Timeout while waiting for flat fields.")

        # Remove camera_events that timed out, removing them from the remaining flat-fielding
        camera_events = {cam_name: value for cam_name, value in camera_events.items(
        ) if value["event"].is_set()}
        return camera_events

    def _take_flat_field_darks(self, exptimes, observation, safety_func, **kwargs):
        """Take the dark flat fields for each camera.

        args:
            exptimes: dict of camera_name: list of exposure times.
            observation: Flat field Observation object.
        """
        # Exposure time lists may not be the same length for each camera
        while True:
            next_exptimes = {}
            for cam_name in exptimes.keys():
                with suppress(KeyError):
                    next_exptimes[cam_name] = exptimes[cam_name].pop()

            # Break if we have finished all the cameras
            if not next_exptimes:
                break

            # Take the exposures, break out if safety fails
            if safety_func():
                self._take_flat_observation(next_exptimes, observation, dark=True, **kwargs)
            else:
                self.logger.debug('Aborting flat-field dark observations as no longer safe.')
                return

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
