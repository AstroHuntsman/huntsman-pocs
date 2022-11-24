import time


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

    # If we do not need to take darks, home the dome and then wait for
    # the twilight max horizon to enter scehduling state
    else:
        # Wait for startup horizon
        if not pocs.observatory.is_past_midnight and not pocs.is_dark(horizon="twilight_max"):
            # perform an initial homing of the dome
            pocs.say("Homing the dome.")
            pocs.observatory.dome.find_home()

            check_delay = pocs.get_config('wait_delay', default=60)
            pocs.say("Waiting for twilight max horizon from starting state.")

            while not pocs.is_dark(horizon="twilight_max"):
                if not pocs.observatory.is_safe(horizon='startup'):
                    pocs.say("Weather has become unsafe while starting, closing dome.")
                    pocs.observatory.close_dome()
                time.sleep(check_delay)

            pocs.say("Finished waiting for twilight max horizon.")
            pocs.next_state = "scheduling"
        elif pocs.observatory.is_past_midnight and not pocs.is_dark(horizon="twilight_max"):
            # in morning after flats park the dome and close the shutter
            pocs.say("It is now the morning, closing the shutter and parking the dome.")
            pocs.observatory.dome.close()
            pocs.say("Shutter is closed: {pocs.observatory.dome.is_closed}")
            pocs.observatory.dome.park()
            pocs.say("Dome is parked: {pocs.observatory.dome.is_parked}")
            pocs.next_state = "sleeping"
