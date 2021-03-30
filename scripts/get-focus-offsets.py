""" Find optimal focus position offsets for each filter, relative to the luminance filter.
It is the user's responsibility to open the dome and slew to an appropriate focusing field.
"""
import json
from panoptes.utils.time import wait_for_events
from huntsman.pocs.utils.huntsman import create_huntsman_pocs

FILTER_NAMES = "luminance", "s_II", "halpha", "r_band", "g_band"
TIMEOUT = 900
REFERENCE_FILTER = "luminance"
OUTPUT_FILENAME = "focus_offsets.json"

if __name__ == "__main__":

    # Get the observatory
    huntsman = create_huntsman_pocs(with_dome=False, simulators=["power", "weather"])
    observatory = huntsman.observatory
    cameras = observatory.cameras

    # Prepare the cameras
    huntsman.say("Preparing cameras.")
    observatory.prepare_cameras()

    # Record optimal focus positions in each filter
    focus_positions = {cam_name: {} for cam_name in cameras.keys()}
    for filter_name in FILTER_NAMES:

        # Do the focusing
        huntsman.say(f"Focusing in {filter_name} filter.")
        events = observatory.autofocus_cameras(filter_name=filter_name, coarse=True)
        wait_for_events(list(events.values()), timeout=TIMEOUT)

        # Store focus positions
        for cam_name, cam in cameras.items():
            focus_positions[cam_name][filter_name] = cam.focuser.position

    # Calculate focus offsets
    focus_offsets = {cam_name: {} for cam_name in cameras.keys()}
    for cam_name in cameras.keys():

        reference_position = focus_positions[cam_name][REFERENCE_FILTER]

        for filter_name in FILTER_NAMES:
            focus_position = focus_positions[cam_name][filter_name]
            focus_offsets[cam_name][filter_name] = focus_position - reference_position

        huntsman.say(f"Focus offsets for camera {cam_name}: {focus_offsets[cam_name]}")

    # Write positions to file
    with open(OUTPUT_FILENAME, 'w') as f:
        json.dump(focus_offsets, f)
