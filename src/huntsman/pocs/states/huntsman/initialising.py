""" The goal of the initialising state is to prepare Huntsman for observing, including opening
the dome and cooling the cameras. Note that it is the responsibility of the state machine to
check it is safe before entering this (and all other) states. """


def on_enter(event_data):
    """
    """
    pocs = event_data.model
    pocs.next_state = 'parking'
    pocs.say("Initialising Huntsman.")

    pocs.observatory.prepare_cameras()
    pocs.observatory.mount.unpark()
    pocs.observatory.open_dome()

    pocs.say("Initialisation complete.")
    pocs.next_state == "ready"  # If not safe, the state machine goes to park automatically
