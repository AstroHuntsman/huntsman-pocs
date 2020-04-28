def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'ready'

    # If it is dark and safe we shouldn't be in sleeping state
    if pocs.is_safe(horizon='focus'):
        msg = "Weather is good and it is dark. Something must have gone wrong."
        pocs.say(msg)
        if not pocs.should_retry:
            pocs.stop_states()
            raise RuntimeError(msg)
    else:
        pocs.say("Another successful night!")
