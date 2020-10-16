def on_enter(event_data):
    """Preparing State.

    This can be used to do any additional setup on the observations.

    This was used primarily for the HDR observations setup.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    try:
        pocs.say("Preparing the observations for our selected target")
        pocs.next_state = 'slewing'
    except Exception as e:
        pocs.logger.warning(f"Problem with preparing state: {e!r}")
