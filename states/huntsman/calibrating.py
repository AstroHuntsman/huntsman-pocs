
def on_enter(event_data):
    """Pointing State

    Take 30 second exposure and plate-solve to get the pointing error
    """
    pocs = event_data.model

    pocs.next_state = 'parking'

    try:

        # Take the flats
        if pocs.observatory.should_take_flats(which='evening'):
            pocs.say("Taking some flat fields to start the night")
            narrow_band_cameras = list()
            broad_band_cameras = list()

            # Collect cameras by filter
            for cam_name, cam in pocs.observatory.cameras.items():
                if cam.filter_type.lower().startswith('ha'):
                    narrow_band_cameras.append(cam.name)
                else:
                    broad_band_cameras.append(cam.name)

            if len(narrow_band_cameras) > 0:
                pocs.say("Starting narrow band flat fields")
                pocs.observatory.take_evening_flats(camera_list=narrow_band_cameras)

            if len(broad_band_cameras) > 0:
                pocs.say("Staring broad band flat fields")
                pocs.observatory.take_evening_flats(camera_list=broad_band_cameras)

            pocs.say("Done taking flat fields.")
    except Exception as e:
        pocs.logger.warning("Problem with flat fielding: {}".format(e))

    # Do a coarse focus to start the night
    try:
        # Wait until dark enough to focus (will send to Home)
        pocs.say("Checking if it's dark enough to focus")
        pocs.wait_until_dark(horizon='focus')

        pocs.say("Coarse focusing all cameras before starting observing for the night")
        autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
        pocs.logger.debug("Started focus, going to wait")
        pocs.wait_for_events([e for e in autofocus_events.values()], 30 * 60)
        pocs.say("Finished with initial coarse forcus for the night")

    except Exception as e:
        pocs.logger.warning("Problem with coarse autofocus: {}".format(e))

    # Wait until dark enough to observe (will send to Home)
    pocs.say("Checking if it's dark enough to observe")
    pocs.wait_until_dark(horizon='observe')

    pocs.next_state = 'scheduling'
