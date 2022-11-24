def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'parked'
    pocs.say("Parking Huntsman.")

    # Clear any current observation
    pocs.observatory.current_observation = None
    # if sun is below startup horizon and weather is safe dont close the dome
    # this is prevent the observatory open and closing if there are no targets
    # to schedule or if its waiting for focus horizon
    # this also helps keep inside dome temp equal to outside
    if not pocs.observatory.is_safe(horizon='startup'):
        pocs.observatory.close_dome()

    pocs.say("I'm takin' it on home and then parking.")
    pocs.observatory.mount.home_and_park()
