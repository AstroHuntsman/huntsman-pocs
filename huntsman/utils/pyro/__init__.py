import Pyro4
from Pyro4 import naming, errors

from huntsman.camera.pyro import CameraServer
from huntsman.utils import get_own_ip, sshfs, DummyLogger
from huntsman.utils.config import load_device_config

#==============================================================================

def run_name_server(host=None, port=None, autoclean=0, logger=None):
    """
    Runs a Pyro name server.

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
    if logger is None:
        logger = DummyLogger()

    try:
        # Check that there isn't a name server already running
        name_server = Pyro4.locateNS()
    except errors.NamingError:
        if not host:
            # Not given an hostname or IP address. Will attempt to work it out.
            host = get_own_ip(verbose=True)
        else:
            host = str(host)

        if port is not None:
            port = int(port)

        Pyro4.config.NS_AUTOCLEAN = float(autoclean)

        logger.info("Starting Pyro name server... (Control-C/Command-C to exit)")
        naming.startNSloop(host=host, port=port)
    else:
        logger.info("Pyro name server {} already running! Exiting...".format(name_server))

#==============================================================================

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

    #Mount the SSHFS images directory
    mountpoint = sshfs.mount_images_dir(logger=logger)

    Pyro4.config.SERVERTYPE = "multiplex"

    #Load the config file
    config = load_device_config(logger=logger, **kwargs)

    #Specify address
    host = config.get('host', None)
    if not host:
        host = get_own_ip(verbose=True)
    port = config.get('port', 0)

    with Pyro4.Daemon(host=host, port=port) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error('Failed to locate Pyro name server: {}'.format(err))
            exit(1)

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

            #Unmount the SSHFS
            if unmount_sshfs:
                sshfs.unmount(mountpoint, logger=logger)

#==============================================================================



