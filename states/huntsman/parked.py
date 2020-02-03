
def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.say("I'm parked now. Phew.")

    pocs.say("Cleaning up for the night!")

    if pocs.is_dark(horizon="flat") and pocs.is_weather_safe is False:
        pocs.next_state = 'taking_darks'
    else:
        pocs.next_state = 'housekeeping'
