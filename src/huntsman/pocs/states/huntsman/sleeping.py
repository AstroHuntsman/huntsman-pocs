from panoptes.utils.error import TheSkyXTimeout
import time


def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'starting'

    # Reset the observing run
    pocs.say("Resetting observing run from sleeping state.")
    pocs.reset_observing_run()

    # in morning after flats park the dome and close the shutter
    if pocs.observatory.is_past_midnight and not pocs.is_dark(horizon="twilight_max"):
        pocs.say("Morning approaches, I must return to my coffin.")
        pocs.observatory.dome.close()
        pocs.say("Shutter is closed: {pocs.observatory.dome.is_closed}")
        pocs.say('Sending dome to park position.')
        n = pocs.get_config('mount.num_park_attempts', default=3)
        for i in range(n):
            try:
                pocs.observatory.dome.park()
            except TheSkyXTimeout:
                if i + 1 < n:
                    pocs.say(
                        f"Attempt {i+1}/{n} at parking dome timed out, waiting 30 seconds and trying again.")
                    time.sleep(30)
                    continue
                else:
                    pocs.say("Max dome parking attempts reached, final attempt timed out.")
                    raise TheSkyXTimeout()
            break
        pocs.say("Dome is parked: {pocs.observatory.dome.is_parked}")

    # if at any point in the nigth we enter the sleeping state with bad weather, close the dome
    if pocs.observatory.dome.is_open and pocs.is_weather_safe():
        pocs.say("Dome is open while weather is unsafe, closing dome.")
        pocs.observatory.close_dome()

    # Wait for startup horizon
    if not pocs.is_dark(horizon="startup"):

        check_delay = pocs.get_config('wait_delay', default=120)

        pocs.say("Waiting for startup horizon from sleeping state.")

        while not pocs.is_dark(horizon="startup"):
            if pocs.observatory.dome.is_open:
                pocs.say("Dome should not be open during the day, closing dome.")
                pocs.observatory.close_dome()
            time.sleep(check_delay)

        pocs.say("Finished waiting for startup horizon.")
