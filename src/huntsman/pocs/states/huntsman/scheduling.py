
def on_enter(event_data):
    """ Determine what to schedule next. """

    pocs = event_data.model
    pocs.next_state = 'parking'

    # First check if a coarse focus is required
    if pocs.is_safe(horizon="focus") and pocs.observatory.coarse_focus_required:
        pocs.say("Scheduled coarse focusing")
        pocs.next_state = "coarse_focusing"
        return

    # Next, check if we should observe
    elif pocs.is_safe(horizon="observe"):

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
