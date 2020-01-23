def on_enter(event_data):
    """taking_darks State
    """
    pocs = event_data.model

    pocs.next_state = 'parking'

    try:
        pocs.say("It's time to take darks!")

        current_observation = pocs.observatory.current_observation

        pocs.logger.debug("Setting coords: {}".format(current_observation.field))

        # Take the darks
        if pocs.observatory.mount.set_target_coordinates(current_observation.field):

            pocs.status()

            # Wait until mount is parked
            pocs.say("I'm going to take next dark field")

            cameras = list()
            for cam_name, cam in pocs.observatory.cameras.items():
                cameras.append(cam_name)

            if len(cameras) > 0:
                pocs.say("Starting narrow band flat fields")
                pocs.observatory.take_dark_fields(camera_list=cameras)

            pocs.next_state = 'parked'

    except Exception as e:
        pocs.logger.warning("Problem with preparing: {}".format(e))
