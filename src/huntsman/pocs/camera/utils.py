import tempfile
from collections import OrderedDict
from contextlib import suppress

import numpy as np
from astropy import units as u

from panoptes.utils.config.client import get_config
from panoptes.utils import error
from panoptes.utils.utils import get_quantity_value

from huntsman.pocs.camera.pyro.client import Camera
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.nameserver import get_running_nameserver
from panoptes.pocs.camera import create_cameras_from_config as create_local_cameras


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
    cameras = OrderedDict()

    config = config or get_config()
    camera_config = config["cameras"]

    if camera_config.get("devices", None) is None:
        logger.info('No camera devices found in config.')
        return cameras

    # Get a config specific to the local cameras
    config_local = camera_config.copy()
    n_local = 0
    with suppress(KeyError):
        del config_local["devices"]
        config_local["devices"] = [c for c in camera_config["devices"] if not c.get(
                                   "is_distributed", False)]
        n_local = len(config_local['devices'])
    logger.debug(f"Found {n_local} local cameras in config.")

    # Get a config specific to the distibuted cameras
    config_distributed = camera_config.copy()
    n_dist = 0
    with suppress(KeyError):
        del config_distributed["devices"]
        config_distributed["devices"] = [c for c in camera_config["devices"] if c.get(
                                         "is_distributed", False)]
        n_dist = len(config_distributed['devices'])
    logger.debug(f"Found {n_dist} distributed cameras in config.")

    # Create local cameras
    if n_local > 0:
        try:
            cameras_local = create_local_cameras(config=config_local, **kwargs)
            cameras.update(cameras_local)
        except Exception as err:
            logger.error(f"Error encountered while creating local cameras: {err}")

    # Create distributed cameras
    if n_dist > 0:
        try:
            cameras_dist = create_distributed_cameras(camera_config=config_distributed)
            cameras.update(cameras_dist)
        except Exception as err:
            logger.error(f"Error encountered while creating distributed cameras: {err}")

    if len(cameras) == 0:
        raise error.CameraNotFound(msg="Failed to create any cameras!")

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

    logger.debug(f"Primary camera: {primary_camera}.")
    logger.debug(f"{len(cameras)} cameras created.")

    return cameras


def create_distributed_cameras(camera_config, metadata=None):
    """Create distributed camera object(s) based on detected cameras and config

    Creates a `pocs.camera.pyro.Camera` object for each distributed camera detected.

    Args:
        camera_config: 'cameras' section from POCS config

    Returns:
        OrderedDict: An ordered dictionary of created camera objects, with the
            camera name as key and camera instance as value. Returns an empty
            OrderedDict if no distributed cameras are found.
    """
    if metadata is None:
        metadata = get_config("pyro.CameraService.metadata", default=None)
    if metadata is not None:
        metadata = set(metadata)

    # Get all distributed cameras
    camera_uris = list_distributed_cameras(ns_host=camera_config.get('name_server_host', None),
                                           metadata=metadata)
    # Create the camera objects.
    # TODO: do this in parallel because initialising cameras can take a while.
    cameras = OrderedDict()
    primary_id = camera_config.get('primary', '')
    for cam_name, cam_uri in camera_uris.items():
        logger.debug(f'Creating camera: {cam_name}')

        cam = Camera(port=cam_name, uri=cam_uri)

        if primary_id == cam.uid or primary_id == cam.name:
            cam.is_primary = True

        logger.info(f"Camera created: {cam}")
        cameras[cam_name] = cam

    return cameras


def list_distributed_cameras(ns_host=None, metadata=None):
    """Detect distributed cameras.

    Looks for a Pyro name server and queries it for the list of registered cameras.

    Args:
        ns_host (str, optional): hostname or IP address of the name server host. If not given
            will attempt to locate the name server via UDP network broadcast.

    Returns:
        dict: Dictionary of detected distributed camera name, URI pairs
    """
    with get_running_nameserver() as name_server:
        camera_uris = name_server.yplookup(meta_all=metadata)
        camera_uris = {k: v[0] for k, v in camera_uris.items()}
        logger.debug(f"Found {len(camera_uris)} cameras on name server.")
    return camera_uris


def tune_exposure_time(camera, target, initial_exptime, min_exptime=0, max_exptime=None,
                       max_steps=5, tolerance=0.1, cutout_size=256, bias=None, **kwargs):
    """ Tune the exposure time to within certain tolerance of the desired counts.
    TODO: Add as camera method.
    """
    camera.logger.info(f"Tuning exposure time for {camera}.")

    # Parse quantities
    initial_exptime = get_quantity_value(initial_exptime, "second") * u.second

    if min_exptime is not None:
        min_exptime = get_quantity_value(min_exptime, "second") * u.second
    if max_exptime is not None:
        max_exptime = get_quantity_value(max_exptime, "second") * u.second

    try:
        bit_depth = camera.bit_depth.to_value("bit")
    except NotImplementedError:
        bit_depth = 16

    saturated_counts = 2 ** bit_depth

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as tf:

        exptime = initial_exptime

        for step in range(max_steps):

            # Check if exposure time is within valid range
            if (exptime == max_exptime) or (exptime == min_exptime):
                break

            # Get an image
            cutout = camera.get_cutout(exptime, tf.name, cutout_size, keep_file=False, **kwargs)
            cutout = cutout.astype("float32")
            if bias is not None:
                cutout -= bias

            # Measure average counts
            normalised_counts = np.median(cutout) / saturated_counts

            # Check if tolerance condition is met
            if tolerance:
                if abs(normalised_counts - target) < tolerance:
                    break

            # Update exposure time
            exptime = exptime * target / normalised_counts
            if max_exptime is not None:
                exptime = min(exptime, max_exptime)
            if min_exptime is not None:
                exptime = max(exptime, min_exptime)

    camera.logger.info(f"Tuned exposure time for {camera}: {exptime}")

    return exptime
