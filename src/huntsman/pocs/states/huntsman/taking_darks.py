def on_enter(event_data):

    pocs = event_data.model
    pocs.next_state = 'housekeeping'

    # Take bias frames
    pocs.observatory.take_bias_frames()

    # Take dark frames
    pocs.observatory.take_dark_frames()
