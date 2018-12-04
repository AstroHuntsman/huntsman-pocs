from collections import OrderedDict
import re
import shutil
import subprocess

import Pyro4

from pocs.utils import error
from pocs.utils import load_module

from huntsman.utils import load_config

from pocs.camera import list_connected_cameras
from pocs.camera import create_cameras_from_config as create_local_cameras
from pocs.camera.camera import AbstractCamera  # pragma: no flakes
from pocs.camera.camera import AbstractGPhotoCamera  # pragma: no flakes

from huntsman.camera.pyro import Camera as PyroCamera

from pocs.utils import logger as logger_module


def list_distributed_cameras(ns_host=None, logger=None):
    """Detect distributed cameras.

    Looks for a Pyro name server and queries it for the list of registered cameras.

    Args:
        host (str, optional): hostname or IP address of the name server host. If not given
            will attempt to locate the name server via UDP network broadcast.
        logger (logging.Logger, optional): logger to use for messages, if not given will
            use the root logger.

    Returns:
        dict: Dictionary of detected distributed camera name, URI pairs
    """
    if not logger:
        logger = logger_module.get_root_logger()

    try:
        # Get a proxy for the name server (will raise NamingError if not found)
        with Pyro4.locateNS(host=ns_host) as name_server:
            # Find all the registered POCS cameras
            camera_uris = name_server.list(metadata_all={'POCS', 'Camera'})
            camera_uris = OrderedDict(sorted(camera_uris.items(), key=lambda t: t[0]))
            n_cameras = len(camera_uris)
            if n_cameras > 0:
                msg = "Found {} distributed cameras on name server".format(n_cameras)
                logger.debug(msg)
            else:
                msg = "Found name server but no distributed cameras"
                logger.warning(msg)
    except Pyro4.errors.NamingError as err:
        msg = "Couldn't connect to Pyro name server: {}".format(err)
        logger.warning(msg)
        camera_uris = OrderedDict()

    return camera_uris


def create_cameras_from_config(config=None, logger=None, **kwargs):
    """Create camera object(s) based on the config.

    Creates a camera for each camera item listed in the config. Ensures the
    appropriate camera module is loaded.

    Args:
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
    if not logger:
        logger = logger_module.get_root_logger()

    if not config:
        config = load_config(**kwargs)

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
        cameras = create_local_cameras(config=config, logger=logger, **kwargs)
    except (error.PanError, KeyError, error.CameraNotFound):
        logger.debug("No local cameras")
        cameras = OrderedDict()

    if not a_simulator and distributed_cameras:
        logger.debug("Creating distributed cameras")
        cameras.update(create_distributed_cameras(camera_info, logger=logger))

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


def create_distributed_cameras(camera_info, logger=None):
    """Create distributed camera object(s) based on detected cameras and config

    Creates a `pocs.camera.pyro.Camera` object for each distributed camera detected.

    Args:
        camera_info: 'cameras' section from POCS config
        logger (logging.Logger, optional): logger to use for messages, if not given will
            use the root logger.

    Returns:
        OrderedDict: An ordered dictionary of created camera objects, with the
            camera name as key and camera instance as value. Returns an empty
            OrderedDict if no distributed cameras are found.
    """
    if not logger:
        logger = logger_module.get_root_logger()

    # Get all distributed cameras
    camera_uris = list_distributed_cameras(ns_host=camera_info.get('name_server_host', None),
                                           logger=logger)

    # Create the camera objects.
    # TODO: do this in parallel because initialising cameras can take a while.
    cameras = OrderedDict()
    primary_id = camera_info.get('primary', '')
    for cam_name, cam_uri in camera_uris.items():
        logger.debug('Creating camera: {}'.format(cam_name))
        cam = PyroCamera(name=cam_name, uri=cam_uri)
        is_primary = ''
        if primary_id == cam.uid or primary_id == cam.name:
            cam.is_primary = True
            is_primary = ' [Primary]'

        logger.debug("Camera created: {} {}{}".format(
            cam.name, cam.uid, is_primary))

        cameras[cam_name] = cam

    return cameras
