"""
State to handle the taking of calibration frames (evening and morning).
"""


def get_cameras(pocs):
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


def wait_for_twilight(pocs):
    '''
    Wait for twilight. Temporary solution until something better is found.
    '''
    pocs.logger.debug('Waiting for twilight...')
    while pocs.is_weather_safe():
        twilight = pocs.is_dark(horizon='flat') and not pocs.is_dark(horizon='focus')
        if not twilight:
            pocs.sleep(delay=pocs._safe_delay)
        else:
            return True
    return False


def on_enter(event_data):
    '''
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.

    If evening, the next state will be coarse_focusing, else, parking.
    '''
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Make sure its safe, dark and light enough for flats
    if not wait_for_twilight(pocs):
        return

    if pocs.observatory.take_flat_fields:

        # Identify filter types
        narrow_band_cameras, broad_band_cameras = get_cameras(pocs)

        # Specify which flats we are taking and in which order
        if pocs.observatory.past_midnight():
            flat_func = pocs.observatory.take_morning_flats
            camera_lists = [broad_band_cameras, narrow_band_cameras]
        else:
            flat_func = pocs.observatory.take_evening_flats
            camera_lists = [narrow_band_cameras, broad_band_cameras]

        # Take flat fields
        for camera_list in camera_lists:
            flat_func(camera_list=camera_list)

    else:
        pocs.say('Skipping twilight flat fields.')

    # Specify the next state
    if pocs.observatory.past_midnight():
        pocs.next_state = 'parking'
    else:
        pocs.next_state = 'coarse_focusing'
