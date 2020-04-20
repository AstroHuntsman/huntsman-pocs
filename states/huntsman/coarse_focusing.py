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

    # Start the autofocusing
    coarse_focus_timeout = pocs.config['focusing']['coarse']['timeout']
    try:
        pocs.say("Coarse focusing all cameras before starting observing for the night.")
        autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
        pocs.logger.debug("Waiting for coarse focus to finish.")
        pocs.wait_for_events(list(autofocus_events.values()), coarse_focus_timeout)

    except Exception as err:
        pocs.logger.warning(f"Problem with coarse autofocus: {err}.")

    pocs.next_state = 'scheduling'
