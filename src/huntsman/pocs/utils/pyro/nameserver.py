from contextlib import suppress
from multiprocessing.context import Process

import Pyro5.errors
from Pyro5.core import locate_ns
from Pyro5.nameserver import start_ns_loop
from huntsman.pocs.utils import error
from huntsman.pocs.utils.config import get_config
from huntsman.pocs.utils.logger import logger


def get_running_nameserver(host=None, port=None, broadcast=True):
    """Attempt to find a running Pyro5 nameserver.

    The `host` and `port` should only be passed if it is well known
    that they will be exact, otherwise it's simpler just to let the
    broadcast do its job.
    """

    host = host or get_config('pyro.nameserver.host', default='localhost')
    port = int(port or get_config('pyro.nameserver.port', default=6564))

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
        host (str, optional): hostname/IP address to bind the name server to. If `None` is given
            (default), will look for the `pyro.nameserver.ip` config entry, otherwise will default
            to localhost.
        port (int, optional): port number to bind the nameserver to. If `None` is given (default),
            will look for the `pyro.nameserver.port` config entry, otherwise will default to `0`,
            which auto-selects a port.
        auto_clean (int, optional): interval, in seconds, for automatic deregistration of objects
            from the name server if they cannot be connected. If not given no autocleaning will
            be done.
        auto_start (bool, optional): If nameserver should be started, which will case the function
            to block. Default is False, which will return the nameserver daemon and it is the users
            responsibility to start the `requestLoop`.

    Returns:
        multiprocess.Process: The process responsible for running the nameserver. Note that if the
            nameserver was started via `autostart=True`, the function will block until terminated,
            but still return the completed process.
    """
    logger.info(f"Pyro nameserver start request: host={host}, port={port}, auto_clean={auto_clean}"
                f", auto_start={auto_start}.")
    host = host or get_config('pyro.nameserver.ip')
    port = int(port or get_config('pyro.nameserver.port', default=0))

    with suppress(error.PyroNameServerNotFound, Pyro5.errors.NamingError):
        logger.info(f'Checking for existing nameserver on {host}:{port}')
        nameserver = get_running_nameserver(host=host, port=port)
        logger.info(f"Pyro nameserver={nameserver} already running.")
        return nameserver

    Pyro5.config.NS_AUTOCLEAN = float(auto_clean)

    # Function to be called inside a separate process to run our nameserver.
    def start_server():
        try:
            start_ns_loop(host=host, port=port, enableBroadcast=True)
        except KeyboardInterrupt:  # noqa
            logger.info(f'Pyro nameserver requested shutdown by user.')
        except Exception as e:  # noqa
            logger.warning(
                f'Problem starting Pyro nameserver, is another nameserver already running?')
            logger.error(f'Error: {e!r}')
        finally:
            logger.info(f'Pyro nameserver shutting down.')

    # Set up nameserver process.
    logger.debug(f'Setting up Pyro nameserver process.')
    server_process = Process(target=start_server)

    if auto_start:
        logger.info("Auto-starting new pyro nameserver")
        server_process.start()
        logger.success(
            "Pyro nameserver started, will block until finished...(Ctrl-c/Cmd-c to exit)")
        server_process.join()

    return server_process
