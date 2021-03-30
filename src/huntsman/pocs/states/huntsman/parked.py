def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.say("I'm parked now. Phew.")
    pocs.next_state = 'housekeeping'
