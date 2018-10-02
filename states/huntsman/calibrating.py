from astropy.coordinates import get_sun

from pocs.utils import current_time
from pocs.utils.flats import wait_for_sun_alt


def on_enter(event_data):
    """Pointing State

    Take 30 second exposure and plate-solve to get the pointing error
    """
    pocs = event_data.model

    pocs.next_state = 'parking'

    try:

        if pocs.observatory.take_flat_fields:

            # Wait for twilight if needed
            while True:
                sun_pos = pocs.observatory.observer.altaz(
                    current_time(),
                    target=get_sun(current_time())
                ).alt

                if sun_pos.value <= 10 and sun_pos.value >= 0:
                    pocs.say("Sun is still not down yet, will wait to take some flats")
                    pocs.sleep(delay=60)
                else:
                    break

            # Take the flats
            if sun_pos.value <= 0 and sun_pos.value >= -12:
                pocs.say("Taking some flat fields to start the night")

                narrow_band_cameras = list()
                broad_band_cameras = list()
                for cam_name, cam in pocs.observatory.cameras.items():
                    if cam.filter_type.lower().startswith('ha'):
                        narrow_band_cameras.append(cam.name)
                    else:
                        broad_band_cameras.append(cam.name)

                if len(narrow_band_cameras) > 0:
                    pocs.say("Starting narrow band flat fields")
                    pocs.observatory.take_evening_flats(camera_list=narrow_band_cameras)  # H-alpha

                if len(broad_band_cameras) > 0:
                    pocs.say("Staring broad band flat fields")
                    pocs.observatory.take_evening_flats(camera_list=broad_band_cameras)   # g and r

    except Exception as e:
        pocs.logger.warning("Problem with flat fielding: {}".format(e))

    # Coarse focus all cameras to start the night.
    # Wait for nautical twilight if needed.
    wait_for_sun_alt(pocs=pocs,
                     max_altitude=-12 * u.degree,
                     message="Done with flat fields, waiting for nautical twilight ({})",
                     delay=60*3)
    try:
        pocs.say("Coarse focusing all cameras before starting observing for the night")
        pocs.observatory.autofocus_cameras(coarse=True)
    except Exception as e:
        pocs.logger.warning("Problem with coarse autofocus: {}".format(e))

    # Wait for astronomical twilight if needed
    wait_for_sun_alt(pocs=pocs,
                     max_altitude=-18 * u.degree,
                     message="Done with calibrations, waiting for astronomical twilight ({})",
                     delay=60*3)

    pocs.next_state = 'scheduling'
