from panoptes.utils import altaz_to_radec
from panoptes.utils.time import current_time
from panoptes.utils.config.client import get_config

from panoptes.pocs.utils.location import create_location_from_config


def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. We now
    decide on the next state and ready the cameras if appropriate.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'
    pocs.observatory.mount.unpark()

    # Check if we need to focus.
    if pocs.is_dark(horizon='focus') and pocs.observatory.coarse_focus_required:
        pocs.next_state = 'coarse_focusing'

    # Check if we should go straight to observing
    elif pocs.is_dark(horizon='observe'):
        pocs.next_state = 'scheduling'

    # Don't need to focus, not dark enough to observe
    else:
        if pocs.observatory.past_midnight:
            if pocs.is_dark(horizon='flat'):
                pocs.next_state = 'twilight_flat_fielding'
            else:
                # Too bright for morning flats, go to parking
                pocs.next_state = 'parking'

        else:
            if pocs.is_dark(horizon='focus'):
                # Evening, don't need to focus but too dark for twilight flats
                pocs.next_state = 'scheduling'
            else:
                pocs.next_state = 'twilight_flat_fielding'

    # Prepare the cameras if we are about to take some exposures
    if pocs.next_state != 'parking':
        pocs.say("Making sure cameras are ready before leaving ready state.")
        pocs.observatory.prepare_cameras()
        if pocs.observatory.has_dome:
            pocs.say("I'm opening the dome.")
        try:
            pocs.observatory.dome.open()
        except AttributeError:
            pocs.logger.warning('Not opening the dome! Observatory has no dome attribute!')
        pocs.say("Ok, I'm all set up and ready to go!")

        if pocs.next_state == 'coarse_focusing':
            # Setup information about location
            pocs.say('Setting up location')
            site_details = create_location_from_config()
            earth_location = site_details['earth_location']

            # Set up the coordinates for coarse focus.
            coarse_focus_config = get_config('focusing.coarse')
            alt = coarse_focus_config['alt']
            az = coarse_focus_config['az']

            coarse_focus_coords = altaz_to_radec(alt=alt, az=az, location=earth_location,
                                                 obstime=current_time())

            pocs.say(f'Coarse focus coordinates: {coarse_focus_coords}')

            # Slew to coordinates for coarse focusing.
            pocs.say("I'm slewing over to the coordinates for coarse focus.")
            pocs.observatory.mount.slew_to_coordinates(coarse_focus_coords)

            pocs.say("I'm at the coordinates for coarse focus.")
