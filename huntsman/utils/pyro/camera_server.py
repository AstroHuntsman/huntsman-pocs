import sys

import Pyro4
from Pyro4 import errors

from huntsman.utils import get_own_ip, sshfs, DummyLogger
from huntsman.utils.config import load_device_config

from huntsman.camera.pyro import CameraServer


def run_camera_server(ignore_local=False, unmount_sshfs=True, logger=None,
                      **kwargs):
    """
    Runs a Pyro camera server.

    The camera server should be run on the camera control computers of distributed cameras. The
    camera servers should be started after the name server, but before POCS.

    Args:
        ignore_local (bool, optional): If True use the default
        $HUNTSMAN_POCS/conf_files/pyro_camera.yaml only. If False will allow
            $HUNTSMAN_POCS/conf_files/pyro_camera_local.yaml to override the default configuration.
            Default False.

        unmount_sshfs (bool, optional): If True, unmounts the sshfs upon
            termination of the camera server.

    """
    if logger is None:
        logger = DummyLogger()

    # Mount the SSHFS images directory
    mountpoint = sshfs.mount_images_dir(logger=logger)

    Pyro4.config.SERVERTYPE = "multiplex"

    # Load the config file
    config = load_device_config(logger=logger, **kwargs)

    # Specify address
    host = config.get('host', None)
    if not host:
        host = get_own_ip(verbose=True)
    # If port is not in config set to 0 so that Pyro will choose a random one.
    port = config.get('port', 0)

    with Pyro4.Daemon(host=host, port=port) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error('Failed to locate Pyro name server: {}'.format(err))
            sys.exit(1)

        logger.info('Found Pyro name server.')
        uri = daemon.register(CameraServer)
        logger.info('Camera server registered with daemon as {}'.format(uri))
        name_server.register(config['name'], uri, metadata={"POCS",
                                                            "Camera",
                                                            config['camera']['model']})
        logger.info('Registered with name server as {}'.format(config['name']))
        logger.info('Starting request loop... (Control-C/Command-C to exit)')

        try:
            daemon.requestLoop()
        finally:
            logger.info('\nShutting down...')
            name_server.remove(name=config['name'])
            logger.info('Unregistered from name server')

            # Unmount the SSHFS
            if unmount_sshfs:
                sshfs.unmount(mountpoint, logger=logger)
