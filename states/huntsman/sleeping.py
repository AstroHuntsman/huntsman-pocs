def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'ready'

    # If it is dark and safe we shouldn't be in sleeping state
    if pocs.is_safe(horizon='flat') and pocs.should_retry is False:
        pocs.stop_states()
        msg = "Weather is good and it is dark. Something must have gone wrong. Stopping loop."
        pocs.say(msg)
        raise RuntimeError(msg)
    else:
        pocs.say("Another successful night!")
