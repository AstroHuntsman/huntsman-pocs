import os
import time
from astropy import units as u
from astropy.io import fits
from astropy import stats

from pocs import utils
from pocs.utils.images import fits as fits_utils


def find_flat_times(observatory, camera_list, target_adu=30000, bias=1000, exp_time=1):
    """ Take saturated pictures at twilight and stop when no longer saturated.

    This function is used to find the time at which saturation no longer occurs.
    A series of `exp_time` images will be taken and once the count falls below
    the `target_adu` then the loop will break and the time will be reported. Images
    are stored under the "flats" directory and have a prefix of "saturated_flat".

    Args:
        observatory (pocs.observatory.observatory): An initialized Observatory instance.
        camera_list (list): A list of cameras to expose with.
        target_adu (int, optional): Once counts fall below this level then the loop stops.
            Defaults to 30,000.
        bias (int, optional): Bias counts in the camera that are removed before check.
            Defaults to 1000.
        exp_time (int, optional): The exposure time to use. Defaults to one (1) second.
    """
    image_dir = observatory.config['directories']['images']

    flat_obs = observatory._create_flat_field_observation()
    exp_times = {cam_name: [exp_time * u.second] for cam_name in camera_list}

    # Loop until detector is not saturated
    while True:
        # If we don't have cameras, break loop (they are removed below)
        if not camera_list:
            break

        observatory.logger.debug(
            "Slewing to flat-field coords: {}".format(flat_obs.field))
        observatory.mount.set_target_coordinates(flat_obs.field)
        observatory.mount.slew_to_target()
        observatory.status()  # Seems to help with reading coords

        fits_headers = observatory.get_standard_headers(observation=flat_obs)

        start_time = utils.current_time()
        fits_headers['start_time'] = utils.flatten_time(
            start_time)  # Common start time for cameras

        camera_events = dict()

        # Take the observations
        for cam_name in camera_list:

            camera = observatory.cameras[cam_name]

            filename = "{}/flats/{}/{}/{}.{}".format(
                image_dir,
                camera.uid,
                flat_obs.seq_time,
                'saturated_flat_{:02d}'.format(flat_obs.current_exp),
                camera.file_extension)

            # Take picture and get event
            camera_event = camera.take_observation(
                flat_obs, fits_headers, filename=filename, exp_time=exp_times[cam_name][-1])

            camera_events[cam_name] = {
                'event': camera_event,
                'filename': filename,
            }

        # Block until done exposing on all cameras
        while not all([info['event'].is_set() for info in camera_events.values()]):
            observatory.logger.debug('Waiting for flat-field image')
            time.sleep(1)

        # Check the counts for each image
        for cam_name, info in camera_events.items():
            img_file = info['filename']
            observatory.logger.debug("Checking counts for {}".format(img_file))

            # Unpack fits if compressed
            if not os.path.exists(img_file) and \
                    os.path.exists(img_file.replace('.fits', '.fits.fz')):
                fits_utils.fpack(img_file.replace(
                    '.fits', '.fits.fz'), unpack=True)

            data = fits.getdata(img_file)

            mean, median, stddev = stats.sigma_clipped_stats(data)

            counts = mean - bias
            observatory.logger.debug("Counts: {}".format(counts))

            if counts < target_adu:
                observatory.logger.info(
                    "Counts are under target_adu level for {}".format(cam_name))

                observatory.logger.info(
                    "Current time: {}".format(utils.current_time(pretty=True)))

                # Camera no longer saturated, remove from list
                del camera_list[cam_name]
            else:
                observatory.logger.debug(
                    "{} still saturated, taking more exposures".format(cam_name))
