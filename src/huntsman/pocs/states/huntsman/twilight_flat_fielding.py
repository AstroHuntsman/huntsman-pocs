"""
State to handle the taking of calibration frames (evening and morning).
"""
from functools import partial


def wait_for_twilight(pocs):
    """
    Wait for twilight. Temporary solution until something better is found.

    Twilight when Sun between flat and focus horizons.
    """
    pocs.logger.debug('Waiting for twilight...')
    while pocs.is_safe(horizon='flat'):
        if pocs.is_dark(horizon='focus'):
            pocs.sleep(delay=pocs._safe_delay)
        else:
            return True
    return False


def safety_func(pocs):
    """ Return True only if safe for flats to continue. """
    return pocs.is_safe(horizon='flat') and not pocs.is_dark(horizon='focus')


def on_enter(event_data):
    """
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.

    If evening, the next state will be coarse_focusing, else, parking.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Make sure it's safe, dark and light enough for flats
    if not wait_for_twilight(pocs):
        return

    if pocs.observatory.flat_fields_required:
        sf = partial(safety_func, pocs=pocs)
        pocs.observatory.take_flat_fields(safety_func=sf)
    else:
        pocs.logger.debug('Skipping twilight flat fields.')

    # Specify the next state
    if pocs.observatory.past_midnight:
        pocs.next_state = 'parking'
    else:
        pocs.next_state = 'coarse_focusing'
