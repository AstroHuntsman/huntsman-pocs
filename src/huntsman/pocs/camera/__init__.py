from collections import OrderedDict

import Pyro4

from panoptes.pocs.camera import create_cameras_from_config as create_local_cameras
from panoptes.utils import error

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.camera.pyro import Camera as PyroCamera
from huntsman.pocs.utils import load_config


def create_cameras_from_config(config=None, **kwargs):
    """Create camera object(s) based on the config.

    Creates a camera for each camera item listed in the config. Ensures the
    appropriate camera module is loaded.

    Args:
        config (dict): The config to use. If the default `None`, then load config.
        **kwargs (dict): Can pass a `cameras` object that overrides the info in
            the configuration file. Can also pass `auto_detect`(bool) to try and
            automatically discover the ports.

    Returns:
        OrderedDict: An ordered dictionary of created camera objects, with the
            camera name as key and camera instance as value. Returns an empty
            OrderedDict if there is no camera configuration items.

    Raises:
        error.CameraNotFound: Raised if camera cannot be found at specified port or if
            auto_detect=True and no cameras are found.
        error.PanError: Description
    """
    config = config or load_config(**kwargs)

    # Helper method to first check kwargs then config
    def kwargs_or_config(item, default=None):
        return kwargs.get(item, config.get(item, default))

    a_simulator = 'camera' in kwargs_or_config('simulator', default=list())
    logger.debug("Camera simulator: {}".format(a_simulator))

    camera_info = kwargs_or_config('cameras', default=dict())

    if not camera_info and not a_simulator:
        logger.info('No camera information in config.')
        return OrderedDict()

    distributed_cameras = kwargs.get('distributed_cameras',
                                     camera_info.get('distributed_cameras', False))

    try:
        cameras = create_local_cameras(config=config, **kwargs)
    except (error.PanError, KeyError, error.CameraNotFound):
        logger.debug("No local cameras")
        cameras = OrderedDict()

    if not a_simulator and distributed_cameras:
        logger.debug("Creating distributed cameras")
        cameras.update(create_distributed_cameras(camera_info))

    if len(cameras) == 0:
        raise error.CameraNotFound(
            msg="No cameras available. Exiting.", exit=True)

    # Find primary camera
    primary_camera = None
    for camera in cameras.values():
        if camera.is_primary:
            primary_camera = camera

    # If no camera was specified as primary use the first
    if primary_camera is None:
        camera_names = sorted(cameras.keys())
        primary_camera = cameras[camera_names[0]]
        primary_camera.is_primary = True

    logger.debug("Primary camera: {}", primary_camera)
    logger.debug("{} cameras created", len(cameras))

    return cameras


def create_distributed_cameras(camera_info):
    """Create distributed camera object(s) based on detected cameras and config

    Creates a `pocs.camera.pyro.Camera` object for each distributed camera detected.

    Args:
        camera_info: 'cameras' section from POCS config

    Returns:
        OrderedDict: An ordered dictionary of created camera objects, with the
            camera name as key and camera instance as value. Returns an empty
            OrderedDict if no distributed cameras are found.
    """
    # Get all distributed cameras
    camera_uris = list_distributed_cameras(ns_host=camera_info.get('name_server_host', None))

    # Create the camera objects.
    # TODO: do this in parallel because initialising cameras can take a while.
    cameras = OrderedDict()
    primary_id = camera_info.get('primary', '')
    for cam_name, cam_uri in camera_uris.items():
        logger.debug('Creating camera: {}'.format(cam_name))
        cam = PyroCamera(port=cam_name, uri=cam_uri)
        if primary_id == cam.uid or primary_id == cam.name:
            cam.is_primary = True

        logger.debug(f"Camera created: {cam}")

        cameras[cam_name] = cam

    return cameras


def list_distributed_cameras(ns_host=None):
    """Detect distributed cameras.

    Looks for a Pyro name server and queries it for the list of registered cameras.

    Args:
        ns_host (str, optional): hostname or IP address of the name server host. If not given
            will attempt to locate the name server via UDP network broadcast.

    Returns:
        dict: Dictionary of detected distributed camera name, URI pairs
    """
    try:
        # Get a proxy for the name server (will raise NamingError if not found)
        with Pyro4.locateNS(host=ns_host) as name_server:
            # Find all the registered POCS cameras
            camera_uris = name_server.list(metadata_all={'POCS', 'Camera'})
            camera_uris = OrderedDict(sorted(camera_uris.items(), key=lambda t: t[0]))
            n_cameras = len(camera_uris)
            if n_cameras > 0:
                logger.debug(f"Found {n_cameras} distributed cameras on name server")
            else:
                logger.warning(f"Found name server but no distributed cameras")
    except Pyro4.errors.NamingError as err:
        logger.warning(f"Couldn't connect to Pyro name server: {err!r}")
        camera_uris = OrderedDict()

    return camera_uris
