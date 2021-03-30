""" The goal of the initialising state is to prepare Huntsman for observing, including unparking
the mount and cooling the cameras. Note that it is the responsibility of the state machine to
check it is safe before entering this (and all other) states. """


def on_enter(event_data):
    """
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    pocs.observatory.prepare_cameras()
    pocs.observatory.mount.unpark()

    if not pocs.is_weather_safe() or not pocs.is_dark(horizon="flat"):  # TODO: Use scheduler?
        pocs.next_state = "taking_darks"
    else:
        pocs.next_state = "ready"  # If not safe, the state machine goes to park automatically
