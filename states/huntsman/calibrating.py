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

            sun_pos = pocs.observatory.observer.altaz(
                current_time(),
                target=get_sun(current_time())
            ).alt

            if sun_pos.value <= 0 and sun_pos.value >= -18:
                pocs.say("Taking some flat fields to start the night")

                narrow_band_cameras = list()
                broad_band_cameras = list()
                for cam in pocs.observatory.cameras:
                    if cam.filter.lower().startswith('ha'):
                        narrow_band_cameras.append(cam.name)
                    else:
                        broad_band_cameras.append(cam.name)

                pocs.observatory.take_evening_flats(camera_list=narrow_band_cameras)  # H-alpha
                pocs.observatory.take_evening_flats(camera_list=broad_band_cameras)   # g and r

        pocs.next_state = 'scheduling'

    except Exception as e:
        pocs.logger.warning("Problem with flat-fielding: {}".format(e))
