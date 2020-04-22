def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. The next step is to
    schedule something for the night.
    """
    pocs = event_data.model

    pocs.say("Ok, I'm all set up and ready to go!")

    pocs.observatory.mount.unpark()

    if pocs.is_dark(horizon='focus'):  # Too dark for twighlight flats
        if pocs.observatory.require_coarse_focus():
            pocs.next_state = 'coarse_focusing'
        else:
            pocs.next_state = 'scheduling'
    else:
        pocs.next_state = 'twilight_flat_fielding'
