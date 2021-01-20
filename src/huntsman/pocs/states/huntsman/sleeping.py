def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'initialising'

    # If it is dark and safe we shouldn't be in sleeping state
    if pocs.is_safe(horizon='focus') and not pocs.should_retry:
        pocs.logger.debug("Safety check passed but in sleeping state. Stopping states.")
        pocs.stop_states()
    else:
        pocs.say("Resetting observing run from sleeping state. Continuing states.")
        pocs.reset_observing_run()
