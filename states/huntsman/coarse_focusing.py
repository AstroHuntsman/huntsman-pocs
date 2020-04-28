"""
State to handle the coarse focusing at the start of the night.
"""


def on_enter(event_data):
    '''
    Coarse focusing state. Will do a coarse focus for each camera and move to
    the scheduling state.
    '''
    pocs = event_data.model
    pocs.next_state = 'parking'

    coarse_focus_timeout = pocs.config['focusing']['coarse']['timeout']

    # Do the autofocusing
    pocs.say("Coarse focusing all cameras before starting observing for the night.")
    autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
    pocs.logger.debug("Waiting for coarse focus to finish.")
    pocs.wait_for_events(list(autofocus_events.values()), coarse_focus_timeout)

    # Morning and not dark enough for observing...
    if pocs.observatory.past_midnight and not pocs.is_dark(horizon='observe'):
        pocs.next_state = 'twilight_flat_fielding'
    else:
        pocs.next_state = 'scheduling'
