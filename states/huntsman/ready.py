def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. The next step is to
    schedule something for the night.
    """
    pocs = event_data.model

    pocs.say("Ok, I'm all set up and ready to go!")

    pocs.observatory.mount.unpark()

    # This will check the config settings and current time to
    # determine if we should take flats.
    if pocs.observatory.should_take_flats(which='evening'):
        pocs.next_state = 'calibrating'
        horizon = 'flat'
    else:
        pocs.next_state = 'scheduling'
        horizon = 'observe'

    if pocs.observatory.is_dark(horizon=horizon) is False:
        pocs.say("Not dark enough yet, going to wait a little while.")
        pocs.wait_until_dark(horizon=horizon)
