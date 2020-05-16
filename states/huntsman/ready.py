import time
from pocs.utils import error


def prepare_cameras(pocs, sleep=60, max_attempts=5):
    """
    Make sure cameras are ready before starting states.
    """
    pocs.logger.debug('Preparing cameras before leaving ready state.')
    cameras = pocs.observatory.cameras.values()

    # Make sure camera cooling is enabled
    for cam in cameras:
        cam.cooling_enabled = True

    # Wait for cameras to be ready
    for i in range(max_attempts):
        if all([cam.is_ready for cam in cameras]):
            return
        time.sleep(sleep)
    raise error.PanError('Timeout while waiting for cameras to become ready from ready state.')


def on_enter(event_data):
    """
    Once in the `ready` state our unit has been initialized successfully. The next step is to
    schedule something for the night.
    """
    pocs = event_data.model
    pocs.next_state = 'parking'
    pocs.say("Ok, I'm all set up and ready to go!")

    pocs.observatory.mount.unpark()

    # Check if we need to foucs
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
        prepare_cameras(pocs)
