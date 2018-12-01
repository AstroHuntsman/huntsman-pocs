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

        self.take_flat_fields = take_flats

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
            exp_times = [target['exp_time'][0]
                         for target in hdr_targets]  # Not sure why exp_time is in tuple

            observation.field = fields
            observation.exp_time = exp_times

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

    def take_evening_flats(self,
                           alt=None,
                           az=None,
                           min_counts=5000,
                           max_counts=15000,
                           bias=1000,
                           max_exptime=60.,
                           camera_list=None,
                           target_adu_percentage=0.5,
                           max_num_exposures=10,
                           *args, **kwargs
                           ):
        """Take flat fields

        Args:
            alt (float, optional): Altitude for flats
            az (float, optional): Azimuth for flats
            min_counts (int, optional): Minimum ADU count
            max_counts (int, optional): Maximum ADU count
            bias (int, optional): Default bias for the cameras
            max_exptime (float, optional): Maximum exposure time before stopping
            camera_list (list, optional): List of cameras to use for flat-fielding
            target_adu_percentage (float, optional): Exposure time will be adjust so
                that counts are close to: target * (`min_counts` + `max_counts`). Default
                to 0.5
            max_num_exposures (int, optional): Maximum number of flats to take
            *args (TYPE): Description
            **kwargs (TYPE): Description

        """
        target_adu = target_adu_percentage * (min_counts + max_counts)

        image_dir = self.config['directories']['images']

        flat_obs = self._create_flat_field_observation(alt=alt, az=az)
        exp_times = {cam_name: [1. * u.second] for cam_name in camera_list}

        # Loop until conditions are met for flat-fielding
        while True:
            self.logger.debug("Slewing to flat-field coords: {}".format(flat_obs.field))
            self.mount.set_target_coordinates(flat_obs.field)
            self.mount.slew_to_target()
            self.status()  # Seems to help with reading coords

            fits_headers = self.get_standard_headers(observation=flat_obs)

            start_time = utils.current_time()
            fits_headers['start_time'] = utils.flatten_time(
                start_time)  # Common start time for cameras

            camera_events = dict()

            # Take the observations
            for cam_name in camera_list:

                camera = self.cameras[cam_name]

                filename = "{}/flats/{}/{}/{}.{}".format(
                    image_dir,
                    camera.uid,
                    flat_obs.seq_time,
                    'flat_{:02d}'.format(flat_obs.current_exp_num), camera.file_extension)

                # Take picture and get event
                if exp_times[cam_name][-1].value < max_exptime:
                    camera_event = camera.take_observation(
                        flat_obs,
                        fits_headers,
                        filename=filename,
                        exp_time=exp_times[cam_name][-1]
                    )

                    camera_events[cam_name] = {
                        'event': camera_event,
                        'filename': filename,
                    }

            # Block until done exposing on all cameras
            while not all([info['event'].is_set() for info in camera_events.values()]):
                self.logger.debug('Waiting for flat-field image')
                time.sleep(1)

            # Check the counts for each image
            is_saturated = False
            for cam_name, info in camera_events.items():
                img_file = info['filename']
                self.logger.debug("Checking counts for {}".format(img_file))

                # Unpack fits if compressed
                if not os.path.exists(img_file) and \
                        os.path.exists(img_file.replace('.fits', '.fits.fz')):
                    fits_utils.fpack(img_file.replace('.fits', '.fits.fz'), unpack=True)

                data = fits.getdata(img_file)

                mean, median, stddev = stats.sigma_clipped_stats(data)

                counts = mean - bias

                # This is in the original DragonFly code so copying
                if counts <= 0:
                    counts = 10

                self.logger.debug("Counts: {}".format(counts))

                if counts < min_counts or counts > max_counts:
                    self.logger.debug("Counts outside min/max range, should be discarded")

                # If we are saturating then wait a bit and redo
                if counts >= max_counts:
                    is_saturated = True

                elapsed_time = (utils.current_time() - start_time).sec
                self.logger.debug("Elapsed time: {}".format(elapsed_time))

                # Get suggested exposure time
                exp_time = int(exp_times[cam_name][-1].value * (target_adu / counts) *
                               (2.0 ** (elapsed_time / 180.0)) + 0.5)
                if exp_time < 1:
                    exp_time = 1
                self.logger.debug("Suggested exp_time for {}: {}".format(cam_name, exp_time))
                exp_times[cam_name].append(exp_time * u.second)

            self.logger.debug("Checking for long exposures")
            # Stop flats if any time is greater than max
            if all([t[-1].value >= max_exptime for t in exp_times.values()]):
                self.logger.debug("Exposure times greater than max, stopping flat fields")
                break

            # Stop flats if we are going on too long
            self.logger.debug("Checking for too many exposures")
            if any([len(t) >= max_num_exposures for t in exp_times.values()]):
                self.logger.debug("Too many flats, quitting")
                break

            self.logger.debug("Checking for saturation")
            if is_saturated and exp_times[cam_name][-1].value < 2:
                self.logger.debug(
                    "Saturated with short exposure, waiting 30 seconds before next exposure")
                max_num_exposures += 1
                time.sleep(30)

        # Add a bias exposure
        for cam_name in camera_list:
            exp_times[cam_name].append(0 * u.second)

        # Record how many exposures we took
        num_exposures = flat_obs.current_exp_num

        # Take darks (just last ten)
        for i in range(num_exposures):
            self.logger.debug("Slewing to dark-field coords: {}".format(flat_obs.field))
            self.mount.set_target_coordinates(flat_obs.field)
            self.mount.slew_to_target()
            self.status()

            for cam_name in camera_list:

                try:
                    exp_time = exp_times[cam_name][i]
                except KeyError:
                    break

                camera = self.cameras[cam_name]

                filename = "{}/flats/{}/{}/{}.{}".format(
                    image_dir,
                    camera.uid,
                    flat_obs.seq_time,
                    'dark_{:02d}'.format(flat_obs.current_exp_num),
                    camera.file_extension)

                # Take picture and wait for result
                camera_event = camera.take_observation(
                    flat_obs,
                    fits_headers,
                    filename=filename,
                    exp_time=exp_time,
                    dark=True
                )

                camera_events[cam_name] = {
                    'event': camera_event,
                    'filename': filename,
                }

            # Will block here until done exposing on all cameras
            while not all([info['event'].is_set() for info in camera_events.values()]):
                self.logger.debug('Waiting for dark-field image')
                time.sleep(1)

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
                                       n_positions=9
                                       ):
        if alt is None and az is None:
            flat_config = self.config['flat_field']['twilight']
            alt = flat_config['alt']
            az = flat_config['az']

        flat_coords = utils.altaz_to_radec(
            alt=alt, az=az, location=self.earth_location, obstime=utils.current_time())

        self.logger.debug("Creating dithered observation")
        field = Field('Evening Flats', flat_coords.to_string('hmsdms'))
        flat_obs = DitheredObservation(field, exp_time=1. * u.second)
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
            exp_times = [flat_obs.exp_time for coord in dither_coords]

            flat_obs.field = fields
            flat_obs.exp_time = exp_times
            flat_obs.min_nexp = len(fields)
            flat_obs.exp_set_size = len(fields)

        self.logger.debug("Flat-field observation: {}".format(flat_obs))

        return flat_obs
