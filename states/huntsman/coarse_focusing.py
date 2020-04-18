"""
State to handle the coarse focusing at the start of the night.
"""


def on_enter(event_data):
    '''
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.

    The next state is scheduling.
    '''
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Start the autofocusing
    coarse_focus_timeout = pocs.config['timeout']['coarse_focus']
    try:
        pocs.say("Coarse focusing all cameras before starting observing for the night.")
        autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
        pocs.logger.debug("Waiting for coarse focus to finish.")
        pocs.wait_for_events(list(autofocus_events.values()), coarse_focus_timeout)

    except Exception as err:
        pocs.logger.warning(f"Problem with coarse autofocus: {err}.")

    pocs.next_state = 'scheduling'
