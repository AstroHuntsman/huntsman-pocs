import yaml as yml
import astropy.units as u
from manual_functions import do_science_setup, take_darks, dans_take_flat_field
import numpy as np
from panoptes.utils import current_time 
from panoptes.utils import wait_for_events
from pocs.mount import create_mount_from_config
from huntsman.pocs.scheduler import create_scheduler_from_config 
from pocs.core import POCS
import time
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.utils import load_config
from panoptes.utils import wait_for_events

from astropy.coordinates import SkyCoord
from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
import astropy.units as u

def setup_observation(target, pi):
    with open("dfw_config.yaml", 'r') as open_file:
        config_dictionary = yml.load(open_file)
    cam_name = config_dictionary[target][pi]['cam_name']
    filter_type = config_dictionary[target][pi]['filter_type']
    initial_focus_position = config_dictionary[target][pi]['focus_position']
    target_name = config_dictionary[target][pi]['target_name']
    exposure_time = config_dictionary[target][pi]['exposure_time']* u.s
    pocs_observation = do_science_setup(cam_name, 
                                    target_name, 
                                    initial_focus_position, 
                                    filter_type,
                                    exposure_time)
    return(pocs_observation) 



def setup_observation_all_cams(target_name, exposure_time):
    with open("dfw_config.yaml", 'r') as open_file:
        config_dictionary = yml.load(open_file)
        
    config = load_config()
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)
    simulators=['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)
    pocs = POCS(observatory) 
    test_observation = pocs.observatory.scheduler.observations[target_name]
    
    for pi in config_dictionary['working_cams']:
        cam_name = config_dictionary[target_name][pi]['cam_name']
        chosen_camera = cameras[cam_name]
        chosen_camera.filterwheel.move_to(config_dictionary[target_name][pi]['filter_type'])
        print(chosen_camera.filterwheel.current_filter)
        chosen_camera.focuser.move_to(config_dictionary[target_name][pi]['focus_position'])
        pocs.observatory.add_camera(cam_name, chosen_camera)
    pocs.observatory.current_observation = test_observation  
       
    return(pocs) 


def dans_take_flat_field(exposure_time, take_darks=False):
    """
    Take a single flat field exposure and an associated dark frame for a given camera.
    We use observatory methods to get consistent FITS headers.
    """
    # Create cameras
    config = load_config()
    cameras = create_cameras_from_config(config=config)
    scheduler = create_scheduler_from_config(config=config)
    mount = create_mount_from_config(config=config)
    mount.initialize()

    # Setup the camera
    camera = cameras[cam_name]
    camera.filterwheel.move_to(filter_name)
    camera.focuser.move_to(focus_position)

    with open("dfw_config.yaml", 'r') as open_file:
        config_dictionary = yml.load(open_file)
        
    # Create observatory
    simulators = ['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)
    pocs = POCS(observatory)
    for pi in config_dictionary['working_cams']:
        cam_name = config_dictionary[target_name][pi]['cam_name']
        chosen_camera = cameras[cam_name]
        chosen_camera.filterwheel.move_to(config_dictionary[target_name][pi]['filter_type'])
        print(chosen_camera.filterwheel.current_filter)
        chosen_camera.focuser.move_to(config_dictionary[target_name][pi]['focus_position'])
        pocs.observatory.add_camera(cam_name, chosen_camera)

    # Make the observation and define FITS headers
    observation = observatory._create_flat_field_observation()
    fits_headers = observatory.get_standard_headers(observation=observation)

    # Prepare cameras (make sure temperature is stable etc)
    observatory.prepare_cameras()

    # Take the flat field, including an ET-matched dark frame
    exptimes = {cam_name: exposure_time}
    observatory._take_flat_observation(exptimes, observation, fits_headers=fits_headers,
                                       dark=False)
    if take_darks:
        camera.filterwheel.move_to("blank")
        observatory._take_flat_observation(exptimes, observation, fits_headers=fits_headers,
                                           dark=True)


def lets_go(num_exposures, pocs, **kwargs):
    print("Let's find those FRB's!")
    for i in range(0,num_exposures):
        print(f'Starting exposure {i:04d}/{num_exposures:04d}')
        try:
            observation_events = pocs.observatory.observe()
            camera_events = list(observation_events.values())
        except Exception as e:
            print(f'ERROR in loop: {e!r}')
            break
        else:
            wait_for_events(camera_events, **kwargs)
        
        

def take_flats_from_config(target, pi, num_exp, darks_bool):
    with open("dfw_config.yaml", 'r') as open_file:
        config_dictionary = yml.load(open_file)
    for filter_chosen in config_dictionary['flats']['filters_list']:
        for i in np.arange(1,num_exp):
            dans_take_flat_field(cam_name = config_dictionary['flats'][pi]['cam_name'], 
                                 filter_name = filter_chosen, 
                                 exposure_time = config_dictionary['flats']['day_exp_times'][filter_chosen]*u.s,
                                 focus_position = config_dictionary['darks'][pi]['focus_position'], 
                                 take_darks=darks_bool)
    
    
def take_darks_from_config(target, pi, n_darks):
    with open("dfw_config.yaml", 'r') as open_file:
        config_dictionary = yml.load(open_file)
        exp_times_units = []
        exposure_time = config_dictionary['darks'][pi]['exposure_time']
        for i in config_dictionary['darks'][pi]['exposure_time']:
            exp_times_units.append(i*u.s)
                
    take_darks(cam_name = config_dictionary['darks'][pi]['cam_name'],
               target_name = target,
               initial_focus_position = config_dictionary['darks'][pi]['focus_position'], 
               filter_type = config_dictionary['darks'][pi]['filter_type'],
               exposure_time = exp_times_units,
               n_darks = n_darks)
    
    
    
