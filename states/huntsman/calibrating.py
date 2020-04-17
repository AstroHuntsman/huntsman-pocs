from astropy.coordinates import get_sun
from astropy import units as u

from pocs.utils import current_time


def _wait_for_twilight(pocs, horizon):
    '''
    Wait for twilight if safe to do so.
    '''
    delay = pocs._safe_delay

    while pocs.is_safe(horizon='flat'):

        if not pocs.is_dark(horizon=horizon):
            pocs.say('Not dark enough for coarse focusing. Waiting...')
            pocs.sleep(delay=delay)
        else:
            return True

    return False


def _get_cameras(pocs):
    '''
    Get lists of narrow and broad band cameras.
    '''
    narrow_band_cameras = list()
    broad_band_cameras = list()
    for cam_name, cam in pocs.observatory.cameras.items():

        # This is a hack. There should be a narrow property in the config...
        if cam.filter_type.lower().startswith('ha'):
            narrow_band_cameras.append(cam_name)
        else:
            broad_band_cameras.append(cam_name)

    return narrow_band_cameras, broad_band_cameras


def on_enter(event_data):
    '''
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.
    '''
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Leave the state if not safe to take calibrations
    if not pocs.is_safe(horizon='flat'):
        print('Exiting calibrating state because it is no longer safe.')
        return

    if pocs.observatory.take_flat_fields:

        try:
            # Identify filter types
            narrow_band_cameras, broad_band_cameras = _get_cameras(pocs)

            # Take calibration frames
            pocs.say("Starting narrow band flat fields")
            pocs.observatory.take_evening_flats(camera_list=narrow_band_cameras)

            pocs.say("Starting broad band flat fields")
            pocs.observatory.take_evening_flats(camera_list=broad_band_cameras)

        except Exception as err:
            pocs.logger.warning(f'Problem with flat fielding: {err}')

    # This code needs to be moved to its own state
    # Wait for twilight
    coarse_focus_timeout = 600  # Put this in a config file
    if not _wait_for_twilight(pocs, horizon='focus'):
        print('Exiting calibrating state because it is no longer safe.')
        return

    try:
        pocs.say("Coarse focusing all cameras before starting observing for the night.")
        autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
        pocs.logger.debug("Waiting for coarse focus to finish.")
        pocs.wait_for_events(list(autofocus_events.values()), coarse_focus_timeout)

    except Exception as e:
        pocs.logger.warning("Problem with coarse autofocus: {}".format(e))

    # Wait for astronomical twilight if needed
    if not _wait_for_twilight(pocs, horizon='observe'):
        return

    pocs.next_state = 'scheduling'
