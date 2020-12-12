def on_enter(event_data):
    """ """
    pocs = event_data.model

    # Clear any current observation
    pocs.observatory.current_observation = None

    pocs.next_state = 'parked'

    if pocs.observatory.has_dome:
        pocs.say("I'm closing the dome.")
    try:
        pocs.observatory.dome.close()
    except AttributeError:
        pocs.logger.warning('Not closing the dome! Observatory has no dome attribute!')
    pocs.say("I'm takin' it on home and then parking.")
    pocs.observatory.mount.home_and_park()
