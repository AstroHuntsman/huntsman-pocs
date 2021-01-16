from panoptes.utils.time import wait_for_events, current_time

from panoptes.utils.utils import altaz_to_radec
from panoptes.pocs.utils.location import create_location_from_config


def on_enter(event_data):
    """ Coarse focusing state.

    Will do a coarse focus for each camera and move to the scheduling state.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Setup information about earth location.
    pocs.say('Setting up location')
    site_details = create_location_from_config()
    earth_location = site_details['earth_location']

    # Set up the coarse focus config.
    coarse_focus_config = pocs.get_config('focusing.coarse')

    # Get timeout, alt, and az from config dict.
    coarse_focus_timeout = coarse_focus_config['timeout']
    coarse_focus_alt = coarse_focus_config['alt']
    coarse_focus_az = coarse_focus_config['az']

    # Convert altaz coordinates to radec.
    coarse_focus_coords = altaz_to_radec(alt=coarse_focus_alt, az=coarse_focus_az,
                                         location=earth_location, obstime=current_time())

    pocs.say(f'Coarse focus coordinates: {coarse_focus_coords}')

    # Slew to coordinates for coarse focusing.
    pocs.say("I'm slewing over to the coordinates for coarse focus.")
    pocs.observatory.mount.slew_to_coordinates(coarse_focus_coords)

    pocs.say("I'm at the coordinates for coarse focus.")

    # Do the autofocusing
    pocs.say("Coarse focusing all cameras.")
    autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)
    pocs.logger.debug("Waiting for coarse focus to finish.")
    wait_for_events(list(autofocus_events.values()), timeout=coarse_focus_timeout)

    # Morning and not dark enough for observing...
    if pocs.observatory.past_midnight and not pocs.is_dark(horizon='observe'):
        pocs.next_state = 'twilight_flat_fielding'
    else:
        pocs.next_state = 'scheduling'
