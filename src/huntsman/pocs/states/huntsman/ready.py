from astropy.coordinates import SkyCoord

from panoptes.utils.config.client import get_config


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
            # Wait until mount is_tracking, then transition to track state
            pocs.say("I'm slewing over to the coordinates to track the target.")

            # Start the mount slewing
            coarse_focus_config = get_config('focusing.coarse')
            ra = coarse_focus_config['dummy_ra']
            dec = coarse_focus_config['dummy_dec']

            coords = SkyCoord(ra, dec, unit="deg")
            pocs.observatory.mount.slew_to_coordinates(coords)

            pocs.say("I'm at the coordinates for coarse focusing")
