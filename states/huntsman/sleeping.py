def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'ready'

    # If it is dark and safe we shouldn't be in sleeping state
    if pocs.is_safe(horizon='focus'):
        pocs.logger.debug("Safety check passed but in sleeping state.")
        if pocs.should_retry:
            pocs.logger.dubug("Continuing states.")
        else:
            pocs.say("Stopping states.")
            pocs.stop_states()
    else:
        pocs.say("Another successful night!")
