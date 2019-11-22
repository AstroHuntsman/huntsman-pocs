def on_enter(event_data):
    """Pointing State
    Take dark fields
    """
    pocs = event_data.model

    pocs.next_state = 'parking'

    try:
        pocs.say("It's time to take darks!")

        current_observation = pocs.observatory.current_observation

        pocs.logger.debug("Setting coords: {}".format(current_observation.field))

        if pocs.observatory.mount.set_target_coordinates(current_observation.field):

            pocs.status()

            # Wait until mount is parked
            pocs.say("I'm going to take next dark")

            pocs.next_state = 'parked'

    except Exception as e:
        pocs.logger.warning("Problem with preparing: {}".format(e))
