from panoptes.utils import current_time 
from panoptes.utils import wait_for_events
from pocs.mount import create_mount_from_config
from huntsman.pocs.scheduler import create_scheduler_from_config 
from pocs.core import POCS
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.utils import load_config
from panoptes.utils import wait_for_events

from astropy.coordinates import SkyCoord
from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
import astropy.units as u


def override_night():
    return(True)


def autofocus(cam_name, filter_type, initial_focus_position, exposure_time, coarse_bool):
    config = load_config()
    cameras = create_cameras_from_config(config)
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)
    chosen_camera.focuser.move_to(initial_focus_position)
    chosen_camera.focuser.autofocus(seconds = exposure_time, blocking = True, keep_files = True, make_plots = True, coarse = coarse_bool)
    
    
def take_flats(cam_name, target_name, initial_focus_position, filter_type, exposure_time):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)
    #mount.initialize()
    
    chosen_camera = cameras[cam_name]
    chosen_camera.filterwheel.move_to(filter_type)    

    # Set to best focus position found
    chosen_camera.focuser.move_to(initial_focus_position)    
    
    simulators=['weather', 'mount', 'power', 'night', 'mount']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)

    pocs = POCS(observatory)    
    pocs.observatory.add_camera(cam_name, chosen_camera)    
    test_observation = pocs.observatory.scheduler.observations[target_name]
    pocs.observatory.current_observation = test_observation    
    test_observation.exptime = exposure_time
    pocs.observatory.take_flat_fields(camera_names = [cam_name],
                                     safety_func = override_night)
    
    
def take_darks(cam_name, target_name, initial_focus_position, filter_type, exposure_time, n_darks):
    # Load Huntsman configuration
    config = load_config()

    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config)
    scheduler = create_scheduler_from_config(config)
    mount = create_mount_from_config(config)
    mount.initialize()
    
    chosen_camera = cameras[cam_name]
    print(chosen_camera.is_ready)
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
    pocs.observatory.take_dark_fields(exptimes = exposure_time, n_darks=n_darks)
    
    
def do_science(cam_name, target_name, initial_focus_position, filter_type, exposure_time):
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
    test_observation.exptime = exposure_time
    pocs.observatory.observe()
    
    
    
def do_science_setup(cam_name, target_name, initial_focus_position, filter_type, exposure_time):
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
    test_observation.exptime = exposure_time
    pocs.observatory.current_observation = test_observation
    
    return(pocs)


def dans_take_flat_field(cam_name, filter_name, exposure_time, focus_position, take_darks=False):
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

    # Create observatory
    simulators = ['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)
    for cam_name, cam in cameras:
        observatory.add_camera(cam_name, cam)
        chosen_camera = cameras[cam_name]
        camera.filterwheel.move_to(filter_name)
        camera.focuser.move_to(focus_position)
        
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

# def take_dark_with_single_camera(field,
#               observation,
#               camera,
#               base_date=None,
#               num_exposures=1,
#               base_dir='/var/huntsman/images/temp',
#               take_flats=False):
#     """Takes pics with the cameras"""

#     # Set a base date for all pics and use that as directory name.
#     base_date = base_date or current_time(flatten=True)
#     exposure_events = []
#     for i in range(num_exposures):
#         print(f"Starting exposures {i:03d} of {num_exposures:03d}.")

#         # Share timestamp filename across all cameras.
#         timestamp = current_time(flatten=True)

#         new_filename = f'{base_dir}/{camera.uid}/{timestamp}.fits'

#         exposure_events.append(camera.take_observation(
#                 observation, filename=new_filename, headers={}, dark=True))
#         print(f"Exposure {new_filename} started.")

#     print(f"Waiting for exposures {i:03d}/{num_exposures:03d}")
#     wait_for_events(exposure_events)
    
    
def take_pic_with_single_camera(field,
              observation,
              camera,
              base_date=None,
              num_exposures=1,
              base_dir='/var/huntsman/images/temp',
              take_flats=False):
    """Takes pics with the cameras"""

    # Set a base date for all pics and use that as directory name.
    base_date = base_date or current_time(flatten=True)
    exposure_events = []
    for i in range(num_exposures):
        print(f"Starting exposures {i:03d} of {num_exposures:03d}.")

        # Share timestamp filename across all cameras.
        timestamp = current_time(flatten=True)

        new_filename = f'{base_dir}/{camera.uid}/{timestamp}.fits'

        exposure_events.append(camera.take_observation(
                observation, filename=new_filename, headers={}))
        print(f"Exposure {new_filename} started.")

    print(f"Waiting for exposures {i:03d}/{num_exposures:03d}")
    wait_for_events(exposure_events)

# def take_pics(field,
#               observation,
#               cameras,
#               base_date=None,
#               num_exposures=1,
#               base_dir='/var/huntsman/images/temp',
#               take_flats=False):
#     """Takes pics with the cameras"""

#     # Set a base date for all pics and use that as directory name.
#     base_date = base_date or current_time(flatten=True)

#     for i in range(num_exposures):
#         print(f"Starting exposures {i:03d} of {num_exposures:03d}.")

#         exposure_events = []

#         # Share timestamp filename across all cameras.
#         timestamp = current_time(flatten=True)
#         for cam_name, camera in cameras.items():
#             new_filename = f'{base_dir}/{base_date}/{camera.uid}/{timestamp}.fits'

#             exposure_events.append(camera.take_observation(
#                 observation, filename=new_filename, headers={}))
#             print(f"Exposure {new_filename} started.")

#         print(f"Waiting for exposures {i:03d}/{num_exposures:03d}")
#         wait_for_events(exposure_events)


