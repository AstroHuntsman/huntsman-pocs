from panoptes.utils.error import TheSkyXTimeout
import time


def on_enter(event_data):
    """

    """
    pocs = event_data.model
    pocs.next_state = 'sleeping'

    pocs.say("Recording all the data for the night (not really yet! TODO!!!).")

    # Cleanup existing observations
    try:
        pocs.observatory.cleanup_observations()
    except Exception as e:
        pocs.logger.warning(f'Problem with cleanup: {e!r}')

    # Turn-off camera cooling
    pocs.say('Shutting down for the night, going to turn off the camera cooling')
    pocs.observatory.camera_group.deactivate_camera_cooling()

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
        except Exception as e:
            pocs.logger.warning(f'Problem occured while parking the dome: {e!r}')
        break

    pocs.say("Ok, looks like I'm done for the day. Time to get some sleep!")
