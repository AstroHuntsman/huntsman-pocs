from panoptes.utils import current_time 
from panoptes.utils import wait_for_events
from pocs.mount import create_mount_from_config
from pocs.scheduler import create_scheduler_from_config 
from pocs.core import POCS
from pocs.mount import create_mount_from_config
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.utils import load_config
from panoptes.utils import wait_for_events

from astropy.coordinates import SkyCoord
from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
import astropy.units as u

    
    
def take_flats(cam_name, target_name, initial_focus_position, filter_type, exposure_time):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)
    mount.initialize()
    
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)    

    # Set to best focus position found
    chosen_camera.focuser.move_to(initial_focus_position)    
    
    simulators=['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)

    pocs = POCS(observatory)    
    pocs.observatory.add_camera(cam_name, chosen_camera)    
    test_observation = pocs.observatory.scheduler.observations[target_name]
    pocs.observatory.current_observation = test_observation    
    test_observation.exptime = exposure_time
    pocs.observatory.take_flat_fields(camera_names = cam_name)
    
    
def take_darks(cam_name, target_name, initial_focus_position, filter_type, exposure_time):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)
    mount.initialize()
    
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)    

    # Set to best focus position found
    chosen_camera.focuser.move_to(initial_focus_position)    
    
    simulators=['weather', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount = mount)

    pocs = POCS(observatory)    
    pocs.observatory.add_camera(cam_name, chosen_camera)    
    test_observation = pocs.observatory.scheduler.observations[target_name]
    pocs.observatory.current_observation = test_observation    
    test_observation.exptime = exposure_time
    pocs.observatory.take_dark_fields(exptimes = exposure_time)
    
    
def do_science(cam_name, target_name, initial_focus_position, filter_type):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)  
    
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)    

    # Set to best focus position found
    chosen_camera.focuser.move_to(initial_focus_position)    
    
    simulators=['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)

    pocs = POCS(observatory)    
    pocs.observatory.add_camera(cam_name, chosen_camera)    
    test_observation = pocs.observatory.scheduler.observations[target_name]
    pocs.observatory.current_observation = test_observation    
    
    pocs.observatory.observe()
    
    
    
def do_science_setup(cam_name, target_name, initial_focus_position, filter_type):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)  
    
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)    

    # Set to best focus position found
    chosen_camera.focuser.move_to(initial_focus_position)    
    
    simulators=['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)

    pocs = POCS(observatory)    
    pocs.observatory.add_camera(cam_name, chosen_camera)    
    test_observation = pocs.observatory.scheduler.observations[target_name]
    pocs.observatory.current_observation = test_observation
    
    return(pocs)
