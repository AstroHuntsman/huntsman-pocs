def on_enter(event_data):
    """taking_darks State
    """
    pocs = event_data.model

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
            for cam_name, camera in pocs.observatory.cameras.items():
                cameras.append(cam_name)

            exptimes = list()
            for target in pocs.scheduler.fields_list:
                exp = target["exptime"].value
                if exp not in exptimes:
                    exptimes.append(exp)

            if len(cameras) > 0:
                pocs.say("Starting dark fields")
                pocs.observatory.take_dark_fields(camera_list=cameras,
                                                  exptimes_list=exptimes)
    except Exception as e:
        pocs.logger.warning("Problem encountered while taking darks: {}".format(e))

    pocs.next_state = 'housekeeping'
