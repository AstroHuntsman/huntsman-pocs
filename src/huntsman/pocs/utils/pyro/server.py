import sys

import Pyro4
from Pyro4 import errors
from Pyro4 import naming

# This import is needed to set up the custom (de)serializers in the same scope
# as the TestServer.
from huntsman.pocs.utils.pyro import serializers
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils import get_own_ip
from huntsman.pocs.utils import sshfs
from huntsman.pocs.utils.config import load_device_config
from huntsman.pocs.camera.pyro import CameraServer
# FIXME (wtgee) - we shouldn't be importing from test files.
from huntsman.pocs.tests.test_pyro_servers import TestServer


def run_name_server(host=None, port=None, autoclean=0):
    """Runs a Pyro name server.

    The name server must be running in order to use distributed cameras with POCS. The name server
    should be started before starting camera servers or POCS.

    Args:
        host (str, optional): hostname/IP address to bind the name server to. If not given then
            get_own_ip will be used to attempt to automatically determine the IP addresses of
            the computer that the name server is being started on.
        port (int, optional): port number to bind the name server to. If not given then the port
            will be selected automatically (usually 9090).
        autoclean (int, optional): interval, in seconds, for automatic deregistration of objects
            from the name server if they cannot be connected. If not given no autocleaning will
            be done.
    """
    try:
        # Check that there isn't a name server already running
        name_server = Pyro4.locateNS()
    except errors.NamingError:
        if not host:
            # Not given an hostname or IP address. Will attempt to work it out.
            host = get_own_ip()
        else:
            host = str(host)

        if port is not None:
            port = int(port)

        Pyro4.config.NS_AUTOCLEAN = float(autoclean)

        logger.info("Starting Pyro name server... (Control-C/Command-C to exit)")
        naming.startNSloop(host=host, port=port)
    else:
        logger.info(f"Pyro name server {name_server} already running! Exiting...")


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


def run_test_server():
    """ Runs a Pyro test server.
    """
    host = get_own_ip()

    with Pyro4.Daemon(host=host) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error('Failed to locate Pyro name server: {}'.format(err))
            sys.exit(1)

        logger.info('Found Pyro name server.')
        uri = daemon.register(TestServer)
        logger.info('Test server registered with daemon as {}'.format(uri))
        name_server.register('test_server', uri, metadata={"POCS", "Test"})
        logger.info('Registered with name server as test_server')
        logger.info('Starting request loop... (Control-C/Command-C to exit)')

        try:
            daemon.requestLoop()
        finally:
            logger.info('\nShutting down...')
            name_server.remove(name='test_server')
            logger.info('Unregistered from name server')


def create_pyro_server(server=None, server_metadata=None):
    """Creates and returns a Pyro Server.

    Parameters
    ----------
    server (object): An instance of a class that has been exposed by Pyro.
    server_metadata (dict): Instance metadata to register with the nameserver.

    Yields
    ------
    Pyro4.Daemon: The configured server daemon. User should call `requestLoop()` to
        start the server instance.

    """
    # Load the config file
    config = load_device_config(**kwargs)

    # Specify address
    host = config.get('host', get_own_ip())

    # If port is not in config set to 0 so that Pyro will choose a random one.
    port = config.get('port', 0)

    server_name = config.get('name', 'Generic Pyro Server')

    Pyro4.config.SERVERTYPE = "multiplex"

    with Pyro4.Daemon(host=host, port=port) as daemon:
        try:
            name_server = Pyro4.locateNS()
            logger.info(f'Found Pyro name server: {name_server}')
        except errors.NamingError as err:
            logger.error(f'Failed to locate Pyro name server {server}: {err!r}')

        uri = daemon.register(server)
        logger.info(f'Camera server {server_name} registered with daemon as: {uri}')

        name_server.register(server_name, uri, metadata=server_metadata)
        logger.info(f'Registered with name server as {server_name}')

        # Yield so we can shutdown properly afterward.
        yield daemon

        logger.info(f'Shutting down {server_name} pyro server...')
        name_server.remove(name=server_name)
        logger.info(f'Unregistered {server_name} from name server')
