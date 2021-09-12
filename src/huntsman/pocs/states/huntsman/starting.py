""" The goal of the initialising state is to prepare Huntsman for observing, including unparking
the mount and cooling the cameras. Note that it is the responsibility of the state machine to
check it is safe before entering this (and all other) states. """


def on_enter(event_data):
    """
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
