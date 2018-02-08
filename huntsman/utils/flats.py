import os
import time
from astropy import units as u
from astropy.io import fits
from astropy import stats
from astropy.coordinates import get_sun

from pocs import utils
from pocs.utils.images import crop_data
from pocs.utils.images import fits as fits_utils
from pocs.utils import current_time


def find_flat_times(observatory,
                    cameras,
                    target_adu=30000,
                    exp_time=1,
                    center_crop=True,
                    crop_width=200
                    ):
    """Take saturated pictures at twilight and stop when no longer saturated.

    This function is used to find the time at which saturation no longer occurs.
    A series of `exp_time` images will be taken and once the count falls below
    the `target_adu` then the loop will break and the time will be reported. Images
    are stored under the "flats" directory and have a prefix of "saturated_flat".

    Args:
        observatory (pocs.observatory.observatory): An initialized Observatory instance.
        cameras (dict): A dict of cameras to expose with with name, obj.
        target_adu (int, optional): Once counts fall below this level then the loop stops.
            Defaults to 30,000.
        exp_time (int, optional): The exposure time to use. Defaults to one (1) second.
        center_crop (bool, optional): Use only the center of the image for saturation calcuation.
            Default True.
        crop_width (int, optional): Size of the center crop. Default 200 pixels.
    """
    image_dir = observatory.config['directories']['images']

    flat_obs = observatory._create_flat_field_observation()
    exp_times = {cam_name: [exp_time * u.second] for cam_name in cameras.keys()}

    camera_bias = dict()

    # Loop until detector is not saturated
    while True:
        sun_pos = observatory.observer.altaz(
            current_time(),
            target=get_sun(current_time())
        ).alt

        # If we don't have cameras, break loop (they are removed below)
        if not cameras:
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

        fits_headers['sun_pos'] = sun_pos

        dark_events = dict()
        camera_events = dict()

        # Take the observations
        for cam_name, camera in cameras.items():

            # Take dark (bias) image (only once)
            if cam_name not in camera_bias:
                dark_filename = "{}/flats/{}/{}/{}.{}".format(
                    image_dir,
                    camera.uid,
                    flat_obs.seq_time,
                    'dark_{:02d}'.format(flat_obs.current_exp),
                    camera.file_extension)

                # Take picture and wait for result
                camera_event = camera.take_observation(
                    flat_obs,
                    fits_headers,
                    filename=dark_filename,
                    exp_time=exp_times[cam_name][-1],
                    dark=True
                )

                dark_events[cam_name] = {
                    'event': camera_event,
                    'filename': dark_filename,
                }

                # Will block here until done exposing on all cameras
                while not all([info['event'].is_set() for info in dark_events.values()]):
                    observatory.logger.debug('Waiting for dark-field image')
                    time.sleep(1)

                dark_data = fits.getdata(dark_filename)
                if center_crop:
                    dark_data = crop_data(dark_data, box_width=crop_width)

                camera_bias[cam_name] = dark_data

            # Start saturated images
            flat_filename = "{}/flats/{}/{}/{}.{}".format(
                image_dir,
                camera.uid,
                flat_obs.seq_time,
                'saturated_flat_{:02d}'.format(flat_obs.current_exp),
                camera.file_extension)

            # Take picture and get event
            camera_event = camera.take_observation(
                flat_obs,
                fits_headers,
                filename=flat_filename,
                exp_time=exp_times[cam_name][-1]
            )

            camera_events[cam_name] = {
                'event': camera_event,
                'filename': flat_filename,
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
            if center_crop:
                data = crop_data(data, box_width=crop_width)

            try:
                data = data - camera_bias[cam_name]
            except Exception:
                observatory.logger.debug("Camera bias not avialable")

            mean, median, stddev = stats.sigma_clipped_stats(data)
            counts = mean

            observatory.logger.debug("Counts: {}".format(counts))

            if counts < target_adu:
                observatory.logger.info(
                    "Counts are under target_adu level for {}".format(cam_name))

                observatory.logger.info(
                    "Current time: {} \t Sun alt: {}".format(
                        utils.current_time(pretty=True),
                        sun_pos
                    ))

                # Camera no longer saturated, remove from list
                del cameras[cam_name]
            else:
                observatory.logger.debug(
                    "{} still saturated, taking more exposures".format(cam_name))

        flat_obs.current_exp += 1
