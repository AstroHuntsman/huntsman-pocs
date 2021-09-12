
def on_enter(event_data):
    """ State logic for starting up.
    This state should only be entered from either the sleeping or taking darks states.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Prepare the hardware
    pocs.observatory.prepare_cameras()
    pocs.observatory.mount.unpark()

    # Check if we need to take darks
    if pocs.should_take_darks:
        pocs.next_state = "taking_darks"

    # If we do not need to take darks, enter scheduling
    else:
        pocs.next_state = "scheduling"
