import os
import sys
import time

from astropy import units as u
from astropy.io import fits
from astropy import stats

from pocs.observatory import Observatory
from pocs.scheduler import constraint
from pocs.scheduler.observation import Field
from pocs.utils import error
from pocs import utils
from pocs.utils.images import fits as fits_utils

from huntsman.guide.bisque import Guide
from huntsman.scheduler.observation import DitheredObservation
from huntsman.utils import dither
from huntsman.utils import load_config


class HuntsmanObservatory(Observatory):

    def __init__(self,
                 with_autoguider=False,
                 hdr_mode=False,
                 take_flats=False,
                 config=None,
                 *args, **kwargs
                 ):
        """Huntsman POCS Observatory

        Args:
            with_autoguider (bool, optional): If autoguider is attached,
                defaults to True.
            hdr_mode (bool, optional): If pics should be taken in HDR mode,
                defaults to False.
            take_flats (bool, optional): If flat field images should be take,
                defaults to False.
            *args: Description
            **kwargs: Description
        """
        # Load the config file
        try:
            assert os.getenv('HUNTSMAN_POCS')
        except AssertionError:
            sys.exit("Must set HUNTSMAN_POCS variable")

        # If we don't receive a config then load a local
        if not config:
            config = load_config()
        super().__init__(config=config, *args, **kwargs)

        self._has_hdr_mode = hdr_mode
        self._has_autoguider = with_autoguider

        self.require_flat_fields = take_flats

        # Attributes for focusing
        self.last_focus_time = None
        self._focus_frequency = config['focusing']['coarse']['frequency'] * \
            u.Unit(config['focusing']['coarse']['frequency_unit'])

        # Creating an imager array object
        if self.has_hdr_mode:
            self.logger.error("HDR mode not support currently")
            # self.logger.info('\tSetting up HDR imager array')
            # self.imager_array = imager.create_imagers()

        if self.has_autoguider:
            self.logger.info("\tSetting up autoguider")
            try:
                self._create_autoguider()
            except Exception as e:
                self._has_autoguider = False
                self.logger.warning("Problem setting autoguider, continuing without: {}".format(e))

##########################################################################
# Properties
##########################################################################

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
        Return True if too much time has elapsed since the previous focus, else False.
        """
        if self.last_focus_time is None:
            return True
        if utils.current_time() - self.last_focus_time > self._focus_frequency:
            return True
        return False

    @property
    def past_midnight(self):
        """Check if it's morning, useful for going into either morning or evening flats."""

        # Get the time of the nearest midnight to now
        midnight = self.observer.midnight(utils.current_time(), which='nearest')

        # If the nearest midnight is in the past, it's the morning...
        return midnight < utils.current_time()

##########################################################################
# Methods
##########################################################################

    def initialize(self):
        """Initialize the observatory and connected hardware """
        super().initialize()

        if self.has_autoguider:
            self.logger.debug("Connecting to autoguider")
            self.autoguider.connect()

    def make_hdr_observation(self, observation=None):
        self.logger.debug("Getting exposure times from imager array")

        if observation is None:
            observation = self.current_observation

        if isinstance(observation, DitheredObservation):

            min_magnitude = observation.extra_config.get('min_magnitude', 10) * u.ABmag
            max_magnitude = observation.extra_config.get('max_magnitude', 20) * u.ABmag
            max_exptime = observation.extra_config.get('max_exptime', 300) * u.second

            # Generating a list of exposure times for the imager array
            hdr_targets = utils.hdr.get_hdr_target_list(imager_array=self.imager_array,
                                                        imager_name='canon_sbig_g',
                                                        coords=observation.field.coord,
                                                        name=observation.field.name,
                                                        minimum_magnitude=min_magnitude,
                                                        maximum_exptime=max_exptime,
                                                        maximum_magnitude=max_magnitude,
                                                        long_exposures=1,
                                                        factor=2,
                                                        dither_parameters={
                                                            'pattern_offset': 5 * u.arcmin,
                                                            'random_offset': 0.5 * u.arcmin,
                                                        }
                                                        )
            self.logger.debug("HDR Targets: {}".format(hdr_targets))

            fields = [Field(target['name'], target['position']) for target in hdr_targets]
            exptimes = [target['exptime'][0]
                        for target in hdr_targets]  # Not sure why exptime is in tuple

            observation.field = fields
            observation.exptime = exptimes

            self.logger.debug("New Dithered Observation: {}".format(observation))

    def finish_observing(self):
        """Performs various cleanup functions for observe.

        Add the latest observation to the exposure list.
        """

        # Lookup the current observation
        image_info = self.db.get_current('observations')
        image_id = image_info['data']['image_id']
        file_path = image_info['data']['file_path']

        # Add most recent exposure to list
        self.current_observation.exposure_list[image_id] = file_path

    def slew_to_target(self):
        """ Slew to target and turn on guiding.

        This is convenience method to slew to the target and turn on the guiding
        given a large separation.

        """
        separation_limit = 0.5 * u.degree

        # Slew to target
        self.mount.slew_to_target()

        self.status()  # Send status update and update `is_tracking`

        # WARNING: Some kind of timeout needed
        while not self.mount.is_tracking and self.mount.distance_from_target() >= separation_limit:
            self.logger.debug("Slewing to target")
            time.sleep(1)

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
        super().analyze_recent()

        return self.current_offset_info

    def autofocus_cameras(self, *args, **kwargs):
        '''
        Override autofocus_cameras to update the last focus time.
        '''
        result = super().autofocus_cameras(*args, **kwargs)

        # Update last focus time
        if not kwargs.get("coarse", False):
            self.last_focus_time = utils.current_time()

        return result

    def take_flat_fields(self, camera_names=None, alt=None, az=None, **kwargs):
        """
        Take flat fields for each camera in each filter, respecting filter priority.

        Args:
            camera_names (list, optional): List of camera names to take flats with.
            alt (float, optional): Altitude for flats.
            az (float, optional): Azimuth for flats.
            min_counts (int, optional): Minimum ADU count.
            max_counts (int, optional): Maximum ADU count.
            bias (int, optional): Default bias for the cameras.
            max_exptime (float, optional): Maximum exposure time before stopping.
            camera_list (list, optional): List of cameras to use for flat-fielding.
            target_adu_percentage (float, optional): Exposure time will be adjust so
                that counts are close to: target * (`min_counts` + `max_counts`). Defaults
                to 0.5.
            max_num_exposures (int, optional): Maximum number of flats to take.
        """
        if camera_names is None:
            cameras_all = self.cameras
        else:
            cameras_all = {c: self.cameras[c] for c in camera_names}

        # Obtain the filter order
        filter_order = self.config['filterwheel']['flat_field_order']
        if self.past_midnight:  # If it's the morning, order is reversed
            filter_order = filter_order[::-1]

        exptimes_dark = {c: [0 * u.second] for c in cameras_all.keys()}  # Add a bias exposure
        for filter_name in filter_order:

            # Get a list of cameras that have this filter
            cameras = {}
            for cam_name, cam in cameras_all.items():
                if cam.filterwheel is None:
                    if cam.filter_type == filter_name:
                        cameras[cam_name] = cam
                elif filter_name in cam.filterwheel.filter_names:
                    cameras[cam_name] = cam

            # Go to next filter if there are no cameras with this one
            if not cameras:
                self.logger.debug(f'No cameras found with {filter_name} filter.')
                continue

            # Create the Observation object
            obs = self._create_flat_field_observation(alt=alt, az=az, filter_name=filter_name)

            # Take the flats for each camera in this filter
            self.logger.info(f'Taking flat fields in {filter_name} filter.')
            exptimes = self._take_autoexposure_flats(cameras, obs, **kwargs)

            # Log the new exposure times we need to take darks with
            for cam_name in cameras.keys():
                exptimes_dark[cam_name].extend(
                    [e for e in exptimes[cam_name] if e not in exptimes_dark[cam_name]])

        # Take darks for each exposure time we used
        self.logger.info('Taking flat field dark frames.')
        for exptime in exptimes_dark:
            self._take_flat_field_darks(exptimes_dark, obs)

##########################################################################
# Private Methods
##########################################################################

    def _create_scheduler(self):
        """ Sets up the scheduler that will be used by the observatory """

        scheduler_config = self.config.get('scheduler', {})
        scheduler_type = scheduler_config.get('type', 'dispatch')

        # Read the targets from the file
        fields_file = scheduler_config.get('fields_file', 'simple.yaml')
        fields_path = os.path.join(self.config['directories'][
                                   'targets'], fields_file)
        self.logger.debug('Creating scheduler: {}'.format(fields_path))

        if os.path.exists(fields_path):

            try:
                # Load the required module
                module = utils.load_module(
                    'huntsman.scheduler.{}'.format(scheduler_type))

                # Simple constraint for now
                # constraints = [constraint.MoonAvoidance()]
                constraints = [constraint.MoonAvoidance(), constraint.Duration(30 * u.deg)]

                # Create the Scheduler instance
                self.scheduler = module.Scheduler(
                    self.observer, fields_file=fields_path, constraints=constraints)
                self.logger.debug("Scheduler created")
            except ImportError as e:
                raise error.NotFound(msg=e)
        else:
            raise error.NotFound(
                msg="Fields file does not exist: {}".format(fields_file))

    def _create_autoguider(self):
        guider_config = self.config['guider']
        guider = Guide(**guider_config)

        self.autoguider = guider

    def _create_flat_field_observation(self, alt=None, az=None,
                                       dither_pattern_offset=5 * u.arcmin,
                                       dither_random_offset=0.5 * u.arcmin,
                                       n_positions=9, filter_name=None,
                                       ):
        if alt is None and az is None:
            flat_config = self.config['flat_field']['twilight']
            alt = flat_config['alt']
            az = flat_config['az']

        flat_coords = utils.altaz_to_radec(
            alt=alt, az=az, location=self.earth_location, obstime=utils.current_time())

        self.logger.debug("Creating dithered observation")
        field = Field('Evening Flats', flat_coords.to_string('hmsdms'))
        flat_obs = DitheredObservation(field, exptime=1. * u.second, filter_name=filter_name)
        flat_obs.seq_time = utils.current_time(flatten=True)

        if isinstance(flat_obs, DitheredObservation):

            dither_coords = dither.get_dither_positions(flat_obs.field.coord,
                                                        n_positions=n_positions,
                                                        pattern=dither.dice9,
                                                        pattern_offset=dither_pattern_offset,
                                                        random_offset=dither_random_offset)

            self.logger.debug("Dither Coords for Flat-field: {}".format(dither_coords))

            fields = [Field('Dither{:02d}'.format(i), coord)
                      for i, coord in enumerate(dither_coords)]
            exptimes = [flat_obs.exptime for coord in dither_coords]

            flat_obs.field = fields
            flat_obs.exptime = exptimes
            flat_obs.min_nexp = len(fields)
            flat_obs.exp_set_size = len(fields)

        self.logger.debug("Flat-field observation: {}".format(flat_obs))

        return flat_obs

    def _take_autoexposure_flats(self, cameras, observation, min_counts=5000, max_counts=15000,
                                 bias=1000, max_exptime=60., target_adu_percentage=0.5,
                                 max_num_exposures=10, filter_name=None, min_saturated_exptime=2,
                                 min_exptime=1, *args, **kwargs):
        """Take flat fields iteratively by automatically estimating exposure times.

        Args:
            cameras (dict): Dict of camera name: Camera pairs.
            filter_names (dict): Dict of filter name for each camera.
        """
        target_adu = target_adu_percentage * (min_counts + max_counts)
        exptimes = {cam_name: [1. * u.second] for cam_name in cameras.keys()}

        # Loop until conditions are met to finish flat-fielding
        exposure_count = 0
        while True:

            # Update the exposure count
            exposure_count += 1

            # Get the FITS headers with a common start time
            start_time = utils.current_time()
            fits_headers = self.get_standard_headers(observation=observation)
            fits_headers['start_time'] = utils.flatten_time(start_time)

            # Take the flat field observations (blocking)
            next_exptimes = {c: exptimes[c][-1] for c in cameras.keys()}
            camera_events = self._take_flat_fields(next_exptimes, observation,
                                                   fits_headers=fits_headers)

            # Check the counts for each image
            is_saturated = False
            for cam_name, info in camera_events.items():
                filename = info['filename']
                self.logger.debug("Checking counts for {}".format(filename))

                # Load the image we just took
                try:
                    data = fits.getdata(filename)
                except FileNotFoundError:
                    data = fits.getdata(filename + '.fz')

                # Calculate average counts per pixel
                mean_counts, _, _ = stats.sigma_clipped_stats(data)
                mean_counts = mean_counts - bias
                self.logger.debug("Counts: {}".format(mean_counts))
                if (mean_counts < min_counts) or (mean_counts > max_counts):
                    self.logger.debug("Counts outside min/max range, should be discarded.")

                # Check if camera is saturated
                if mean_counts >= max_counts:
                    is_saturated = True

                # Get suggested exposure time
                elapsed_time = (utils.current_time() - start_time).sec
                exptime = exptimes[cam_name][-1].value * (target_adu / mean_counts)
                # Account for the sky changing brightness
                sky_factor = 2.0 ** (elapsed_time / 180.0)
                if self.past_midnight:
                    exptime = exptime / sky_factor
                else:
                    exptime = exptime * sky_factor
                exptime = int(max(min_exptime, exptime))
                exptimes[cam_name].append(exptime * u.second)
                self.logger.debug("Elapsed time: {}".format(elapsed_time))
                self.logger.debug("Suggested exptime for {}: {}".format(cam_name, exptime))

            # Stop flats if any time is greater than max
            exptime_too_long = [t[-1].value >= max_exptime for t in exptimes.values()]
            if any(exptime_too_long) and not self.past_midnight:
                self.logger.debug("Exposure times greater than max, stopping flat fields.")
                break

            # Stop flats if we have taken too many.
            if any([len(t) >= max_num_exposures for t in exptimes.values()]):
                self.logger.debug("Too many flats, quitting.")
                break

            # Handle saturated cameras
            if is_saturated and exptimes[cam_name][-1].value < min_saturated_exptime:
                if self.past_midnight:
                    self.logger.debug('Saturated with short exposure. Stopping flat fields.')
                    break
                else:
                    self.logger.debug('Saturated with short exposure. Waiting 30 seconds'
                                      'before next exposure.')
                    max_num_exposures += 1
                    time.sleep(30)

        # Return the exposure times
        return exptimes

    def _take_flat_fields(self, exptimes, observation, fits_headers=None, dark=False):
        """
        Slew to flat field, take exposures and wait for them to complete.
        Returns a list of camera events for each camera.

        args:
            exptimes: dict of camera_name: list of exposure times.
            observation: Flat field Observation object.
        """
        image_dir = self.config['directories']['images']
        imtype = 'dark' if dark else 'flat'
        if fits_headers is None:
            fits_headers = self.get_standard_headers(observation=observation)

        # Slew to field
        self.logger.debug(f'Slewing to {imtype}-field coords: {observation.field}.')
        self.mount.set_target_coordinates(observation.field)
        self.mount.slew_to_target()
        self.status()  # Seems to help with reading coords

        # Loop over cameras...
        camera_events = {}
        for cam_name, exptime in exptimes.items():
            cam = self.cameras[cam_name]

            # Define filename for flat fields
            filename = (f'{image_dir}/flats/{cam.uid}/{observation.seq_time}'
                        f'/{imtype}_{observation.current_exp_num:02d}.{cam.file_extension}')

            # Take exposure and get event
            exptime = exptime.to(u.second).value
            camera_event = cam.take_observation(observation, fits_headers,
                                                filename=filename, exptime=exptime)
            camera_events[cam_name] = {'event': camera_event, 'filename': filename}

        # Block until done exposing on all cameras
        while not all([info['event'].is_set() for info in camera_events.values()]):
            self.logger.debug('Waiting for flat-field images...')
            time.sleep(1)

        return camera_events

    def _take_flat_field_darks(self, exptimes, observation):
        """Take the dark fileds for each camera.

        args:
            exptimes: dict of camera_name: list of exposure times.
            observation: Flat field Observation object.
        """
        # Exposure time lists may not be the same length for each camera
        while True:
            next_exptimes = {}
            for cam_name, exptime in exptimes.items():
                try:
                    next_exptimes[cam_name] = exptimes[cam_name].pop(0)
                except IndexError:  # No more exposures left for this camera
                    continue
                self._take_flat_fields(next_exptimes, observation, dark=True)
            # Break if we have finished all the cameras
            if not next_exptimes.items():
                break
