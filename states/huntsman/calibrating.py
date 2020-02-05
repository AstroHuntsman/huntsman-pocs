from astropy.coordinates import get_sun
from astropy import units as u

from pocs.utils import current_time


def wait_for_sun_alt(pocs,
                     min_altitude=None,
                     max_altitude=None,
                     delay=None,
                     message="Waiting for Sun altitude. Current: {}"):
    """
    Wait for the altitude of the Sun to be within given limits

    Args:
        pocs :
        min_altitude (astropy.units.Quantity, optional):
        max_altitude (astropy.units.Quantity, optional):
        message (str):
    """
    if min_altitude is None and max_altitude is None:
        raise ValueError("At least one of min_altitude & max_altitude must be given")
    if min_altitude is None:
        min_altitude = -90
    if max_altitude is None:
        max_altitude = 90
    if isinstance(min_altitude, u.Quantity):
        min_altitude = min_altitude.to(u.degree).value
    if isinstance(max_altitude, u.Quantity):
        max_altitude = max_altitude.to(u.degree).value

    if not delay:
        delay = pocs._safe_delay

    while pocs.is_safe():
        sun_pos = pocs.observatory.observer.altaz(current_time(),
                                                  target=get_sun(current_time())
                                                  ).alt
        if sun_pos.value > max_altitude or sun_pos.value < min_altitude:
            # Check simulator for 'night'
            if 'night' in pocs.config['simulator']:
                pocs.logger.info(f'Using night simulator, pretending sun down.')
                break
            else:
                pocs.say(message.format(sun_pos.value))
                pocs.sleep(delay=delay)
        else:
            break


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
                        narrow_band_cameras.append(cam_name)
                    else:
                        broad_band_cameras.append(cam_name)

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
                     message="Done with flat fields, waiting for nautical twilight for  ({:.02f})")
    try:
        pocs.say("Coarse focusing all cameras before starting observing for the night")
        autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
        pocs.logger.debug("Started focus, going to wait")
        pocs.wait_for_events(autofocus_events.values(), 600)  # Longer timeout?

    except Exception as e:
        pocs.logger.warning("Problem with coarse autofocus: {}".format(e))

    # Wait for astronomical twilight if needed
    wait_for_sun_alt(pocs=pocs,
                     max_altitude=-18 * u.degree,
                     message="Done with calibrations, waiting for astronomical twilight ({:.02f})")

    pocs.next_state = 'scheduling'
