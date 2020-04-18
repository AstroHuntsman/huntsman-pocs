"""
State to handle the taking of calibration frames (evening and morning).
"""
from pocs.utils import current_time


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


def _past_midnight(pocs):
    '''
    Check if is morning, useful for going into either morning or evening flats.
    '''
    # Get the time of the nearest midnight to now
    midnight = pocs.observatory.observer.midnight(current_time(), which='nearest')

    # If the nearest midnight is in the past, its the morning...
    return midnight < current_time()


def on_enter(event_data):
    '''
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.

    If evening, the next state will be coarse_focusing, else, parking.
    '''
    pocs = event_data.model
    pocs.next_state = 'parking'

    if pocs.observatory.take_flat_fields:
        try:
            # Identify filter types
            narrow_band_cameras, broad_band_cameras = _get_cameras(pocs)

            # Take calibration frames
            pocs.say("Starting narrow band flats.")
            pocs.observatory.take_evening_flats(camera_list=narrow_band_cameras)

            pocs.say("Staring broad band flats.")
            pocs.observatory.take_evening_flats(camera_list=broad_band_cameras)

        except Exception as err:
            pocs.logger.warning(f'Problem with flat fielding: {err}')
    else:
        pocs.say('Skipping calibration frames.')

    # Specify the next state
    if _past_midnight(pocs):
        pocs.logger.debug('Finished morning calibrations.')
        pocs.next_state = 'parking'
    else:
        pocs.logger.debug('Finished evening calibrations.')
        pocs.next_state = 'coarse_focusing'
