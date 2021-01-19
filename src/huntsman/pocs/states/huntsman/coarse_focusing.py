from panoptes.utils.time import CountdownTimer
from panoptes.utils.time import current_time
from panoptes.utils.utils import altaz_to_radec


def on_enter(event_data):
    """ Coarse focusing state.

    Will do a coarse focus for each camera and move to the scheduling state.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'

    # Setup information about earth location.
    pocs.say('Setting up location')

    # Set up the coarse focus config.
    coarse_focus_config = pocs.get_config('focusing.coarse')

    # Get timeout, alt, and az from config dict.
    coarse_focus_timeout = coarse_focus_config['timeout']
    coarse_focus_alt = coarse_focus_config['alt']
    coarse_focus_az = coarse_focus_config['az']

    # Convert altaz coordinates to radec.
    coarse_focus_coords = altaz_to_radec(alt=coarse_focus_alt, az=coarse_focus_az,
                                         location=pocs.observatory.earth_location,
                                         obstime=current_time())

    pocs.say(f'Coarse focus coordinates: {coarse_focus_coords}')

    # Slew to coordinates for coarse focusing.
    pocs.say("I'm slewing over to the coordinates for coarse focus.")
    pocs.observatory.mount.slew_to_coordinates(coarse_focus_coords)
    pocs.say("I'm at the coordinates for coarse focus.")

    # Do the autofocusing (non-blocking).
    pocs.say("Starting coarse focus on all cameras.")
    autofocus_events = pocs.observatory.autofocus_cameras(coarse=True)

    timer = CountdownTimer(coarse_focus_timeout)
    pocs.logger.debug("Waiting for coarse focus to finish.")

    while True:
        # Check if all cameras are finished and proceed if so.
        if all([e.is_set() for e in autofocus_events.values()]):
            break

        # If overall timer has expired, check which cameras have not finished
        # and remove them from the observatory.
        if timer.expired():
            pocs.logger.info(f'Autofocus timer expired, checking which cameras were successful')
            for cam_name, focus_event in autofocus_events.items():
                if not focus_event.is_set():
                    pocs.logger.warning(f'Incomplete focus event on {cam_name}, removing')
                    # TODO figure out why and also mark them for restart somehow.
                    # See https://github.com/AstroHuntsman/huntsman-pocs/issues/304
                    pocs.observatory.remove_camera(cam_name)

            # Timer has expired, so proceed
            break
        else:
            timer.sleep(max_sleep=2)  # Not sure what would be best here.

    # If we have removed all the cameras because of incomplete focus, go to park.
    if pocs.observatory.has_cameras:
        # Morning and not dark enough for observing...
        if pocs.observatory.past_midnight and not pocs.is_dark(horizon='observe'):
            pocs.next_state = 'twilight_flat_fielding'
        else:
            pocs.next_state = 'scheduling'
