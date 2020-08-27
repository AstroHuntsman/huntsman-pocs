from contextlib import suppress

import Pyro5.errors
from Pyro5.api import Daemon as PyroDaemon
from Pyro5.api import locate_ns
from Pyro5.api import start_ns

from panoptes.utils.config.client import get_config
from panoptes.utils.config.client import set_config
from panoptes.utils import error

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils import error
from panoptes.utils.library import load_module


def get_running_nameserver(host=None, port=None, broadcast=True):
    """Attempt to find a running Pyro5 nameserver.

    The `host` and `port` should only be passed if it is well known
    that they will be exact, otherwise it's simpler just to let the
    broadcast do its job.
    """

    host = host or get_config('pyro.nameserver.ip')
    port = port or get_config('pyro.nameserver.port')

    logger.info(f'Looking for nameserver on {host}:{port}')
    name_server = locate_ns(host=host, port=port, broadcast=broadcast)
    logger.success(f'Found Pyro name server: {name_server}')

    return name_server


def pyro_nameserver(host=None,
                    port=None,
                    auto_clean=0,
                    auto_start=False):
    """Runs a Pyro name server.

    The name server must be running in order to use distributed cameras with POCS. The name server
    should be started before starting camera servers or POCS.

    Args:
        host (str, optional): hostname/IP address to bind the name server to. If not given then
            get_own_ip will be used to attempt to automatically determine the IP addresses of
            the computer that the name server is being started on.
        port (int, optional): port number to bind the name server to. If not given then the port
            will be selected automatically (usually 9090).
        auto_clean (int, optional): interval, in seconds, for automatic deregistration of objects
            from the name server if they cannot be connected. If not given no autocleaning will
            be done.
        auto_start (bool, optional): If nameserver should be started, which will case the function
            to block. Default is False, which will return the nameserver daemon and it is the users
            responsibility to start the `requestLoop`.
    """
    logger.info(f'Pyro nameserver start request: {host=} {port=} {auto_clean=} {auto_start=}')
    host = host or get_config('pyro.nameserver.ip')
    port = port or get_config('pyro.nameserver.port')

    with suppress(error.PyroNameServerNotFound, Pyro5.errors.NamingError):
        logger.info('Checking for existing nameserver')
        nameserver = get_running_nameserver(host=host, port=port)
        logger.info(f"Pyro {nameserver=} already running.")
        return

    Pyro5.config.NS_AUTOCLEAN = float(auto_clean)

    nameserver_uri, nameserver_daemon, broadcast_server = start_ns(host=host, port=port, enableBroadcast=True)

    logger.info(f'Pyro nameserver started on {nameserver_uri.host}:{nameserver_uri.port} with {auto_start=}')

    try:
        if auto_start:
            logger.success("Auto-starting new pyro nameserver...(Ctrl-c/Cmd-c to exit)")
            nameserver_daemon.requestLoop()
        else:
            logger.debug(f'Yielding Pyro nameserver daemon...')
            yield nameserver_daemon
    finally:
        logger.info(f'Pyro nameserver shutting down.')
        nameserver_daemon.close()


def pyro_service(service_class=None,
                 service_name=None,
                 host=None,
                 port=None,
                 auto_start=True):
    """Creates and runs a Pyro Service.

    This is the "server" portion of the Pyro communication, which should be started
    on a remote device (not on the central control computer).

    Parameters
    ----------
    service_class (class): A class that has been exposed by Pyro.
    service_metadata (dict): Instance metadata to register with the nameserver.
    """
    # Specify address
    host = host or get_config('control_computer.pyro.ip', default='localhost')
    # If port is not in config set to 0 so that Pyro will choose a random one.
    port = port or get_config('control_computer.pyro.port', default=0)

    service_name = service_name or get_config('name', 'Generic Pyro Server')

    # TODO figure out if we really want multiplex.
    Pyro5.config.SERVERTYPE = "multiplex"

    try:
        nameserver = get_running_nameserver(host=host, port=port)
    except Exception as e:
        logger.warning(
            f"Pyro nameserver not running, can't create server. See 'huntsman-pyro nameserver' for details. {e!r}")
        return

    # Get the class for the service.
    service_class_ref = load_module(service_class)

    with PyroDaemon(host=host, port=port) as daemon:
        logger.info(f'Creating pyro daemon service for {service_class=}')
        uri = daemon.register(service_class_ref)
        logger.info(f'{service_class} registered with pyro daemon as: {uri}')

        nameserver.register(service_name, uri, safe=True)
        logger.info(f'Registered {service_class} with name server as {service_name}')

        # Save uri in the generic POCS config.
        # TODO do better checks if config-server is running rather than just a warning.
        try:
            set_config(f'pyro.devices.{service_name}.uri', uri)
        except Exception as e:
            logger.warning(f"Can't save {service_name} uri in config-server: {e!r}")

        try:
            if auto_start:
                logger.success(f"Auto-starting {service_name} service...(Ctrl-c/Cmd-c to exit)")
                daemon.requestLoop()
            else:
                logger.debug(f'Yielding Pyro service daemon for {service_name}...')
                yield daemon
        except KeyboardInterrupt:
            logger.info(f'Shutting down pyro service {service_name=} at {uri=}...')
        except Exception as e:  # noqa
            logger.info(f'{service_name} died unexpectedly: {e!r}')
        finally:
            logger.info(f'Shutting down {service_name} pyro server...')
            nameserver.remove(name=service_name)
            logger.info(f'Unregistered {service_name} from pyro nameserver')
