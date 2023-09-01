
def on_enter(event_data):
    """ Determine what to schedule next. """

    pocs = event_data.model
    pocs.next_state = 'parking'

    # First wait for all the cameras to be ready (in case an exposure was interrupted)
    # sleep interval is 1/5 of the current observation exposure time, repeated 5 times
    try:
        current_obs_exptime = pocs.observatory.current_observation.exptime.value
        sleep_interval = current_obs_exptime/5
    except Exception as err:
        pocs.logger.warning(f"Error getting current observation exposure time: {err!r}")
        sleep_interval = 60
    pocs.say(f"Waiting for cameras to be ready in 5 intervals of {sleep_interval} seconds.")
    pocs.observatory.camera_group.wait_until_ready(sleep=sleep_interval, max_attempts=5)

    # First check if a coarse focus is required
    if pocs.is_dark(horizon="focus") and pocs.observatory.coarse_focus_required:
        pocs.say("Scheduled coarse focusing")
        pocs.next_state = "coarse_focusing"
        return

    # Next, check if we should observe
    elif pocs.is_dark(horizon="observe"):

        try:
            observation = pocs.observatory.get_observation()  # Sets current observation
            pocs.logger.info(f"Observation: {observation}")

        except Exception as err:
            pocs.logger.warning(f"Error getting observation: {err!r}")
            return

        pocs.say(f"Scheduled observation: {observation.name}")
        pocs.next_state = "observing"
        return

    # Finally, check if we should be flat fielding
    elif pocs.observatory.is_twilight and pocs.observatory.flat_fields_required:
        pocs.say("Scheduled twilight flat fielding")
        pocs.next_state = "twilight_flat_fielding"
        return

    # Check if we need to take darks
    if pocs.should_take_darks:
        pocs.next_state = "taking_darks"

    # If we've got this far, nothing to schedule so park
    else:
        pocs.next_state = 'parking'
        pocs.say(f"Nothing to schedule. Going to {pocs.next_state}.")
