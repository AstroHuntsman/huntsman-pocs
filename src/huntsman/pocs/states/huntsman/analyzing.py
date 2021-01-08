def on_enter(event_data):
    """ """
    pocs = event_data.model

    observation = pocs.observatory.current_observation

    pocs.say(f"Analyzing image {observation.current_exp_num} / {observation.min_nexp}")

    pocs.next_state = 'dithering'
    try:
        pocs.observatory.analyze_recent()
    except Exception as err:
        pocs.logger.error(f"Problem in analyzing: {err}")

    if pocs.get_config('actions.FORCE_RESCHEDULE'):
        pocs.say("Forcing a move to the scheduler")

    # Check for minimum number of exposures
    if observation.current_exp_num >= observation.min_nexp:

        # Check if we have completed an exposure block
        if observation.current_exp_num % observation.exp_set_size == 0:
            pocs.next_state = 'scheduling'
