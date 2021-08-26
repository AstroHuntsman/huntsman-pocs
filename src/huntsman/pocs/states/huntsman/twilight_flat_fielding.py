""" Twilight flat fielding state """


def on_enter(event_data):
    """
    Calibrating state. If safe to do so, take flats and darks. Should be
    called once at the beginning and end of the night.

    If evening, the next state will be coarse_focusing, else, parking.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Make sure it's safe, dark and light enough for flats
    is_safe = pocs.wait_for_twilight()
    if not is_safe:
        return

    if pocs.observatory.flat_fields_required:
        pocs.observatory.take_flat_fields()
    else:
        pocs.logger.debug('Skipping twilight flat fields.')

    # Check if we should keep taking flats
    if pocs.observatory.is_twilight and pocs.repeat_flats:
        pocs.logger.info("Taking another round of twilight flat fields")
        pocs.next_state = "twilight_flat_fielding"

    # Check if the Sun is coming up and we need to park
    elif pocs.observatory.is_past_midnight:
        pocs.next_state = 'parking'

    # Check if we need to focus
    else:
        pocs.next_state = 'coarse_focusing'
