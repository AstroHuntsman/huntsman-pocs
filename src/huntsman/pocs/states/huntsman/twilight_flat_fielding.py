""" Twilight flat fielding state """

from huntsman.pocs.error import NotTwilightError, NotSafeError


def on_enter(event_data):
    """ State logic for twilight flat fielding.
    """
    pocs = event_data.model
    pocs.next_state = 'scheduling'

    try:
        pocs.observatory.take_flat_fields()

    # Continue with state if NotTwilightError is raised
    except NotTwilightError:
        pocs.logger.info("No longer twilight. Moving to next state.")

    # If not safe, go to parking
    except NotSafeError:
        pocs.logger.warning("Safety failed while taking twilight flats. Going to park.")
        pocs.next_state = 'parking'
        return

    # Catch and log otherwise unhandled errors
    except Exception as err:
        pocs.logger.error(f"Error taking flat fields: {err!r}. Continuing with states.")
