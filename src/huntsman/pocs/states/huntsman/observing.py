
def on_enter(event_data):

    pocs = event_data.model
    pocs.say("I'm exploring the universe!")
    pocs.next_state = 'scheduling'

    observation = pocs.observatory.current_observation

    try:
        pocs.observatory.take_observation_block(observation)
    except Exception as err:
        pocs.logger.error(f"Exception while taking observation block for {observation}: {err!r}")
