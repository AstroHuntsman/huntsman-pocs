from astropy.coordinates import get_sun

from pocs.utils import current_time


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

        pocs.next_state = 'scheduling'

        # Wait for astronomical sunset if needed
        while True:
            sun_pos = pocs.observatory.observer.altaz(
                current_time(),
                target=get_sun(current_time())
            ).alt

            if sun_pos.value >= -12:
                pocs.say("Done with calibration frames, waiting for astronomical sunset ({})".format(sun_pos.value))
                pocs.sleep(delay=60*3)
            else:
                break

    except Exception as e:
        pocs.logger.warning("Problem with flat-fielding: {}".format(e))
