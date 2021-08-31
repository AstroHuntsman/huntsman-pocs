from panoptes.utils import error


def on_enter(event_data):
    """
    In the `scheduling` state we attempt to find a field using our scheduler. If field is found,
    make sure that the field is up right now (the scheduler should have taken care of this). If
    observable, set the mount to the field and calls `start_slewing` to begin slew.

    If no observable targets are available, `park` the unit.
    """
    pocs = event_data.model
    pocs.next_state = 'observing'

    # If it is not dark enough to observe, go back to ready state
    # The ready state will then decide whether to park, focus, take flats etc
    if not pocs.is_dark(horizon='observe'):
        pocs.say('Not dark enough to continue scheduling. Going back to the ready state.')
        pocs.next_state = "ready"
        return

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
