from pocs.utils import current_time


def past_midnight(pocs):
    '''
    Check if is morning, useful for going into either morning or evening flats.
    '''
    # Get the time of the nearest midnight to now
    midnight = pocs.observatory.observer.midnight(current_time(), which='nearest')

    # If the nearest midnight is in the past, its the morning...
    return midnight < current_time()


def wait_for_twilight(pocs):
    '''
    Wait for the Sun to be between flat and focus horizons.
    '''
    while pocs.is_dark(horizon='focus') or not pocs.is_dark(horizon='flat'):
        pocs.sleep(delay=pocs._safe_delay)
