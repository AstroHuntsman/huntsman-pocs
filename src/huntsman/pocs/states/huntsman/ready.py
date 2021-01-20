""" Once in the "ready" state, Huntsman has been initialized successfully and it is safe. The goal
of the ready state is to decide which of the following states to enter next:
- parking
- coarse_focusing
- scheduling
- twilight_flat_fielding
"""


def on_enter(event_data):
    """
    """
    pocs = event_data.model

    # Check if we need to focus.
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
