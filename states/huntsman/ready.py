def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. The next step is to
    schedule something for the night.
    """
    pocs = event_data.model

    pocs.say("Ok, I'm all set up and ready to go!")

    pocs.observatory.mount.unpark()

    # Check if we need to foucs
    if pocs.is_dark(horizon='focus') and pocs.observatory.require_coarse_focus():
        pocs.next_state = 'coarse_focusing'

    # Check if we should go straight to observing
    elif pocs.is_dark(horizon='observe'):
        pocs.next_state = 'scheduling'

    # Don't need to focus, not dark enough to observe
    elif pocs.observatory.past_midnight():
        if pocs.is_dark(horizon='flat'):
            pocs.next_state = 'twilight_flat_fielding'
        else:
            # We don't want to be waiting all day to take evening flats
            pocs.next_state = 'parking'
    else:
        pocs.next_state = 'twilight_flat_fielding'
