from huntsman.utils.states import past_midnight, wait_for_twilight


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

    # Focusing complete, not dark enough to observe
    elif not past_midnight(pocs):
        if pocs.is_dark(horizon='focus'):
            pocs.next_state = 'scheduling'
        else:
            pocs.next_state = 'twilight_flat_fielding'

    # Focusing complete, not dark enough to observe and morning
    else:
        if pocs.is_dark(horizon='focus'):
            wait_for_twilight(pocs)
        pocs.next_state = 'twilight_flat_fielding'
