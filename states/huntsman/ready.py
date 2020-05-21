def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. The next step is to
    schedule something for the night.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'
    pocs.say("Ok, I'm all set up and ready to go!")

    pocs.observatory.mount.unpark()

    # Check if we need to foucs
    if pocs.is_dark(horizon='focus') and pocs.observatory.coarse_focus_required:
        pocs.next_state = 'coarse_focusing'

    # Check if we should go straight to observing
    elif pocs.is_dark(horizon='observe'):
        pocs.next_state = 'scheduling'

    # Don't need to focus, not dark enough to observe
    else:
        if pocs.observatory.past_midnight:
            if pocs.is_dark(horizon='flat'):
                pocs.next_state = 'twilight_flat_fielding'
            else:
                # Too bright for morning flats, go to parking
                pocs.next_state = 'parking'

        else:
            if pocs.is_dark(horizon='focus'):
                # Evening, don't need to focus but too dark for twilight flats
                pocs.next_state = 'scheduling'
            else:
                pocs.next_state = 'twilight_flat_fielding'

    # Prepare the cameras if we are about to take some exposures
    if pocs.next_state != 'parking':
        pocs.say("Those cameras are hot! Let's turn on the cooling. This might take a few minutes.")
        pocs.observatory.prepare_cameras()
