from panoptes.utils.error import TheSkyXTimeout
import time


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

    # sometimes parking seems to arbitrarily time out, allow for n retries before raising error
    n = pocs.get_config('mount.num_park_attempts', default=3)
    home_timeout = pocs.get_config('mount.home_timeout', default=180)
    park_timeout = pocs.get_config('mount.park_timeout', default=180)
    for i in range(n):
        try:
            pocs.observatory.mount.home_and_park(
                home_timeout=home_timeout, park_timeout=park_timeout)
        except TheSkyXTimeout:
            if i + 1 < n:
                pocs.say(
                    f"Attempt {i+1}/{n} at parking timed out, waiting 30 seconds and trying again.")
                time.sleep(30)
                continue
            else:
                pocs.say("Max parking attempts reached, final attempt timed out.")
                raise TheSkyXTimeout()
        except Exception as e:
            pocs.logger.warning(f'Problem occured while parking the mount: {e!r}')
        break
