from huntsman.pocs.error import NoDarksDuringTwilightError


def on_enter(event_data):

    pocs = event_data.model
    pocs.next_state = 'starting'

    # Take bias frames
    pocs.say("Taking bias frames.")
    try:
        pocs.observatory.take_dark_observation(bias=True)
    except AttributeError as err:
        pocs.logger.warning(f"AttributeError raised while taking biases: {err!r}")
    except NoDarksDuringTwilightError as err:
        pocs.logger.warning(f"Aborting attempt to take darks as it is currently twilight: {err!r}")
        return

    # Take dark frames
    pocs.say("Taking dark frames.")
    try:
        pocs.observatory.take_dark_observation()
    except AttributeError as err:
        pocs.logger.warnng(f"AttributeError raised while taking darks: {err!r}")
    except NoDarksDuringTwilightError as err:
        pocs.logger.warning(f"Aborting attempt to take darks as it is currently twilight: {err!r}")
        return

    # Register the completion of the dark state
    pocs.register_dark_state_completion()
