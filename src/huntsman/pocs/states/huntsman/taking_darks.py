def on_enter(event_data):

    pocs = event_data.model
    pocs.next_state = 'housekeeping'

    # Take bias frames
    pocs.say("Taking bias frames.")
    pocs.observatory.take_bias_observation()

    # Take dark frames
    pocs.say("Taking dark frames.")
    pocs.observatory.take_dark_observation()
