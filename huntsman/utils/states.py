"""
Utilities used by the state machine.
"""


def wait_for_twilight(pocs, horizon, safe_horizon='flat', message=None):
    '''
    Wait for twighlight if safe to do so.
    '''
    delay = pocs._safe_delay

    while pocs.is_safe(horizon=safe_horizon):

        if not pocs.is_dark(horizon=horizon):
            if message is None:
                message = 'Waiting for twilight...'
            pocs.say(message)
            pocs.sleep(delay=delay)
        else:
            return True

    return False


def past_midnight(pocs):
    '''
    Check if is morning, useful for going into either morning or evening flats.
    '''
    time = pocs.siderial_time()
    if (time.hour > 0) & (time.hour <= 12):
        return True
    return False
