
def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.say("I'm parked now. Phew.")

    pocs.say("Cleaning up for the night!")

    if pocs.is_dark() and not pocs.is_weather_safe():
        pocs.next_state = 'taking_darks'
    else:
        pocs.logger.info("Conditions for dark fields are not met")
        pocs.next_state = 'housekeeping'
