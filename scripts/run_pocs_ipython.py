import random
import time

from panoptes.utils import wait_for_events

from pocs.mount import create_mount_from_config
from pocs.core import POCS

from huntsman.pocs.scheduler import create_scheduler_from_config 
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory

from huntsman.pocs.utils import load_config

from astropy.coordinates import SkyCoord
import astropy.units as u

from helpers import get_selection

print("Loading POCS config")
config = load_config()

cameras = create_cameras_from_config(config)
scheduler = create_scheduler_from_config(config)
mount = create_mount_from_config(config)

# Don't take pics if low space
disk_space_required = 25 * u.GB

simulators=['weather', 'mount', 'power', 'night', 'dome']

print(f"Setting up Huntsman Observatory and POCS w/ simulators={simulators}")
observatory = HuntsmanObservatory(scheduler=scheduler, 
        simulators=simulators, mount=mount, cameras=cameras)

pocs = POCS(observatory) 
print("Initilizing POCS")
pocs.initialize()

# Set default
target = 'Test Target'


def show_targets():
    """Show a list of available targets"""
    print("Available Targets:\n")
    current_target_name = ''
    if pocs.observatory.current_observation:
        current_target_name = pocs.observatory.current_observation.name

    obs_list = list(pocs.observatory.scheduler.observations.keys())
    for target_name in obs_list:
        selected = ' <- current\n' if target_name == current_target_name else '\n'
        print(f"\t{target_name}", end=selected)


# Show targets at startup
show_targets()


def select_target(**kwargs):
    """Show the target list and give menu for selection. Will call setup_target"""
    obs_list = list(pocs.observatory.scheduler.observations.keys())
    new_target = get_selection(obs_list, **kwargs)

    if new_target is not None:
        print(f"Setting new target to {new_target}\n")
        setup_target(new_target)


def setup_target(target_name):
    """Initializes the given target and prepares cameras"""
    test_observation = pocs.observatory.scheduler.observations[target_name]
    print(f'Setting current observation to {test_observation}')
    pocs.observatory.current_observation = test_observation  

    for cam_name, cam in pocs.observatory.cameras.items():
        # Get the camera/filter pair for this observation
        filter_name = test_observation.filter_list[cam_name]
        print(f'Setting filter={filter_name} for {cam_name}')
        cam.filterwheel.move_to(filter_name)

        # Look up the initial focus position from config - this could be per filter.
        focus_position = pocs.config['cameras']['initial_focus'][cam_name]
        print(f'Setting focus_position={focus_position} for {cam_name}')
        cam.focuser.move_to(focus_position)
        print()
       
    print(f'Cameras set for {test_observation}')

    
def take_calibrations(num_exposures, day_flats = True, exp_time_dict = {'g_band':0.0005*u.s, 'r_band': 0.002*u.s, 'luminance': 0.0005*u.s}):
    if day_flats:
        observation = pocs.observatory._create_flat_field_observation()
        # I will change this!!! Should not be hardcoded
        for i in range(0, num_exposures):
            print(f'Starting calibration exposures {i:04d}/{num_exposures:04d}, please wait...', end=' ')
            
            fits_headers = pocs.observatory.get_standard_headers(observation=observation)
            camera_exp_times = {}
            for cam_name, cam in pocs.observatory.cameras.items():
                pocs.observatory.add_camera(cam_name, cam)
                current_filter = cam.filterwheel.current_filter
                exposure_time = exp_time_dict[current_filter]
                camera_exp_times[cam_name] = exposure_time
            pocs.observatory.prepare_cameras()
            pocs.observatory._take_flat_observation(camera_exp_times, observation, fits_headers=fits_headers, dark=False)
        


def lets_go(num_exposures, **kwargs):
    """GO GO GO!!!"""
    print(f"Looking for 👽 at {pocs.observatory.current_observation.field}")
    for i in range(0, num_exposures):
        if pocs.has_free_space(required_space=disk_space_required) is False:
            print("Disk space getting full, stopping loop")
            return

        print(f'Starting exposure {i:04d}/{num_exposures:04d}, please wait...', end=' ')
        try:
            observation_events = pocs.observatory.observe()
            camera_events = list(observation_events.values())
        except Exception as e:
            print(f'ERROR in loop: {e!r}')
            break
        else:
            try:
                print("exposure started.")
                wait_for_events(camera_events, **kwargs)
            except KeyboardInterrupt:
                print("Command cancelled. Waiting for current exposure to end then stopping loop.")
                print("Press Ctrl-c again to kill now")
                wait_for_events(camera_events)
                print("Finished current exposure, stopping loop")
                break


        

