from panoptes.utils.error import TheSkyXTimeout


def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'parked'
    pocs.say("Parking Huntsman.")

    # Clear any current observation
    pocs.observatory.current_observation = None
    pocs.observatory.close_dome()

    pocs.say("I'm takin' it on home and then parking.")

    # sometimes parking seems to arbitrarily time out, allow for n retries before raising error
    n = pocs.get_config('mount.num_park_attempts', default=3)
    for i in range(n):
        try:
            pocs.observatory.mount.home_and_park()
        except TheSkyXTimeout:
            if i + 1 < n:
                pocs.say(f"Attempt {i+1}/{n} at parking timed out, trying again.")
                continue
            else:
                pocs.say("Max parking attempts reached, final attempt timed out.")
                raise TheSkyXTimeout()
        break
