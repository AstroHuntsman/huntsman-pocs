from panoptes.utils import error


def on_enter(event_data):
    """
    In the `scheduling` state we attempt to find a field using our scheduler. If field is found,
    make sure that the field is up right now (the scheduler should have taken care of this). If
    observable, set the mount to the field and calls `start_slewing` to begin slew.

    If no observable targets are available, `park` the unit.
    """
    pocs = event_data.model
    pocs.next_state = 'preparing'

    if pocs.run_once and len(pocs.observatory.scheduler.observed_list) > 0:
        pocs.say('Looks like we only wanted to run once, parking now.')

    else:
        pocs.say("Selecting the next target to observe...")
        existing_observation = pocs.observatory.current_observation

        # Get the next observation
        try:
            observation = pocs.observatory.get_observation()
            pocs.logger.info(f"Observation: {observation}")

        except error.NoObservation:
            pocs.say("No valid observations found. Going back to the ready state.")
            pocs.next_state = 'ready'
            return

        except Exception as e:
            pocs.logger.warning(f"Error in scheduling: {e!r}. Going back to the ready state.")
            pocs.next_state = 'ready'
            return

        if existing_observation and observation.name == existing_observation.name:
            pocs.say(f"I'm sticking with {observation.name}.")
            pocs.observatory.current_observation = existing_observation

        else:
            pocs.say(f"I'm going to check out: {observation.name}.")
            if not pocs.observatory.mount.set_target_coordinates(observation.field):
                pocs.logger.warning("Unable to set mount coordinates. Parking.")
                pocs.next_state = "parking"
                return
