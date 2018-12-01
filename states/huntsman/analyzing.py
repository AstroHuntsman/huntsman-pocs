def on_enter(event_data):
    """ """
    pocs = event_data.model

    observation = pocs.observatory.current_observation

    pocs.say("Analyzing image {} / {}".format(observation.current_exp_num, observation.min_nexp))

    pocs.next_state = 'observing'
    try:

        pocs.observatory.analyze_recent()

    except Exception as e:
        pocs.logger.error("Problem in analyzing: {}".format(e))
        #pocs.next_state = 'parking'

    if pocs.force_reschedule:
        pocs.logger.debug('Forcing a reschedule')
        pocs.next_state = 'scheduling'

    # Check for minimum number of exposures
    if observation.current_exp_num >= observation.min_nexp:
        # Check if we have completed an exposure block
        if observation.current_exp_num % observation.exp_set_size == 0:
            pocs.next_state = 'scheduling'

