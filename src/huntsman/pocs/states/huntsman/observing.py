def on_enter(event_data):
    # breakpoint()

    pocs = event_data.model
    pocs.say("I'm exploring the universe!")
    pocs.next_state = 'scheduling'

    observation = pocs.observatory.current_observation

    print("observation.__class__.__name__: ", observation.__class__.__name__)

    # breakpoint()

    try:
        if 'Movie' in observation.__class__.__name__:
            pocs.observatory.take_recording_block(observation)
        else:
            pocs.observatory.take_observation_block(observation)
    except Exception as err:
        pocs.logger.error(
            f"Exception while taking observation block for {observation}: {err!r}"
        )
