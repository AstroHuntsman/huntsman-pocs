import re
import sys

import Pyro4
from Pyro4 import naming, errors
from Pyro4.util import SerializerBase
from astropy import units as u
from astropy.io.misc import yaml as ayaml

from pocs.utils import error

from huntsman.camera.pyro import CameraServer
from huntsman.utils import get_own_ip, sshfs, DummyLogger
from huntsman.utils.config import load_device_config

# Enable local display of remote tracebacks
sys.excepthook = Pyro4.util.excepthook

# Serialisers/deserialisers
name_pattern = re.compile(r"error\.(\w+)'>$")


def panerror_to_dict(obj):
    """Serialiser function for POCS custom exceptions."""
    name_match = name_pattern.search(str(obj.__class__))
    if name_match:
        exception_name = name_match.group(1)
    else:
        msg = f"Unexpected obj type: {obj}, {obj.__class__}"
        raise ValueError(msg)

    return {"__class__": "PanError",
            "exception_name": exception_name,
            "args": obj.args}


def dict_to_panerror(class_name, d):
    """Deserialiser function for POCS custom exceptions."""
    try:
        exception_class = getattr(error, d['exception_name'])
    except AttributeError:
        msg = f"error module has no exception class {exception_name}."
        raise AttributeError(msg)

    return exception_class(*d["args"])


def astropy_to_dict(obj):
    """Serializer function for Astropy objects using astropy.io.misc.yaml.dump()."""
    return {"__class__": "astropy_yaml",
            "yaml_dump": ayaml.dump(obj)}


def dict_to_astropy(class_name, d):
    """De-serialiser function for Astropy objects using astropy.io.misc.yaml.load()."""
    return ayaml.load(d["yaml_dump"])


SerializerBase.register_class_to_dict(u.Quantity, astropy_to_dict)
SerializerBase.register_dict_to_class("astropy_yaml", dict_to_astropy)

SerializerBase.register_class_to_dict(error.PanError, panerror_to_dict)
SerializerBase.register_dict_to_class("PanError", dict_to_panerror)


class NewError(Exception):
    pass

@Pyro4.expose
class TestServer(object):

    def quantity_argument(self, q):
        assert isinstance(q, u.Quantity)

    def quantity_return(self):
        return 42 * u.km * u.ng / u.Ms

    def raise_runtimeerror(self):
        raise RuntimeError("This is a test RuntimeError.")

    def raise_assertionerror(self):
        assert False

    def raise_panerror(self):
        raise error.PanError("This is a test PanError.")

    def raise_timeout(self):
        raise error.Timeout("This is a test Timeout.")

    def raise_notsupported(self):
        raise error.NotSupported("This is a test NotSupported.")

    def raise_illegalvalue(self):
        raise error.IllegalValue("This is a test IllegalValue.")

    def raise_undeserialisable(self):
        raise NewError("Pyro can't de-serialise this.")

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

def run_test_server(logger=None):
    """
    Runs a Pyro test server.
    """
    if logger is None:
        logger = DummyLogger()

    host = get_own_ip(verbose=True)

    with Pyro4.Daemon(host=host) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error('Failed to locate Pyro name server: {}'.format(err))
            exit(1)

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
