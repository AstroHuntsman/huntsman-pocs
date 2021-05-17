from panoptes.utils import error
from time import sleep

WAIT_INTERVAL = 15


def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.say("I'm exploring the universe!")
    pocs.next_state = 'parking'

    observation = pocs.observatory.current_observation

    # If the observation is complete, break and go to scheduling
    if observation.set_is_finished:
        pocs.next_state = 'scheduling'
        return

    #











    try:
        # Start the observing
        camera_events = pocs.observatory.observe()

        wait_time = 0.
        while not all([event.is_set() for event in camera_events.values()]):
            pocs.logger.debug(f'Waiting for images: {wait_time} seconds.')
            sleep(WAIT_INTERVAL)
            wait_time += WAIT_INTERVAL

    except error.Timeout:
        pocs.logger.error("Timeout while waiting for images. Parking.")
    except Exception as e:
        pocs.logger.error(f"Error encountered during exposures: {e}")
    else:
        # Perform some observe cleanup
        pocs.logger.info("Finished observing, setting next state to 'analyzing'.")
        pocs.next_state = 'analyzing'
