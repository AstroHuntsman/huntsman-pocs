import sys

import Pyro4
from Pyro4 import errors

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils import get_own_ip, sshfs
from huntsman.pocs.utils.config import load_device_config

from huntsman.pocs.camera.pyro import CameraServer


def run_camera_server(unmount_sshfs=True, **kwargs):
    """Runs a Pyro camera server.

    This should be run on the camera control computer for a distributed camera.

    The configuration for the camera is read from the pyro_camera.yaml/pyro_camera_local.yaml
    config file. The camera servers should be started after the name server, but before POCS.

    Args:
        unmount_sshfs (bool, optional): If True, unmounts the sshfs upon
            termination of the camera server.

    """
    # Load the config file
    config = load_device_config(**kwargs)

    # Mount the SSHFS images directory
    mountpoint = sshfs.mount_images_dir(config=config)

    # Specify address
    host = config.get('host', get_own_ip())

    # If port is not in config set to 0 so that Pyro will choose a random one.
    port = config.get('port', 0)

    Pyro4.config.SERVERTYPE = "multiplex"

    with Pyro4.Daemon(host=host, port=port) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error(f'Failed to locate Pyro name server: {err!r}')
            sys.exit(1)

        logger.info(f'Found Pyro name server: {name_server}')
        uri = daemon.register(CameraServer)
        logger.info(f'Camera server registered with daemon as: {uri}')
        name_server.register(config['name'], uri, metadata={"POCS",
                                                            "Camera",
                                                            config['camera']['model']})
        logger.info('Registered with name server as {}'.format(config['name']))
        logger.info(f'Starting request loop at {uri}... (Control-C/Command-C to exit)')

        try:
            daemon.requestLoop()
        except KeyboardInterrupt:
            logger.info(f'Shutting down name server at {uri}...')
        except Exception as e:  # noqa
            logger.info(f'Name server died: {e!r}')
        finally:
            name_server.remove(name=config['name'])
            logger.info('Unregistered from name server')

            # Unmount the SSHFS
            if unmount_sshfs:
                logger.info(f'Unmounting {mountpoint}')
                sshfs.unmount(mountpoint)
