from multiprocessing import Process

import Pyro5.errors
from Pyro5.api import Daemon as PyroDaemon

from panoptes.utils.config.client import set_config
from panoptes.utils.library import load_module

from huntsman.pocs.utils.config import get_config
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.nameserver import get_running_nameserver
from huntsman.pocs.utils.config import get_own_ip


def pyro_service(service_class=None,
                 service_name=None,
                 host=None,
                 port=None,
                 auto_start=True,
                 metadata=None):
    """Creates and runs a Pyro Service.

    This is the "server" portion of the Pyro communication, which should be started
    on a remote device (not on the central control computer).

    Parameters
    ----------
    service_class (str): The class that has been exposed by Pyro.
    service_name (str): A name for the service that will be registered with the nameserver. Will
        attempt to use service_name to query the config server for the device config.
    host (str): The host or ip of the device running the service.
    port (str or int): The port to attach the device to, default 0/None for auto-select.
    auto_start (bool): If the pyro service process should automatically be started.
    metadata (list of str): Metadata to be stored on the NS. If `None`, will create metadata
        based on service class using the config server.

    Returns:
        multiprocess.Process: The process responsible for running the service. Note that if the
            service was started via `autostart=True`, the function will block until terminated,
            but still return the completed process.
    """
    # Specify address
    host = host or get_config(f'pyro.{service_name}.ip', default=None)
    if host is None:
        host = get_own_ip(verbose=True)
    # If port is not in config set to 0 so that Pyro will choose a random one.
    port = int(port or get_config(f'pyro.{service_name}.port', default=0))
    # Specify metadata to be stored on NS
    if metadata is None:
        service_class_base = service_class.split(".")[-1]
        metadata = get_config(f"pyro.{service_class_base}.metadata", None)
    if metadata is not None:
        metadata = set(metadata)

    # Get the class instance to expose
    service_name = service_name or get_config('name', 'Generic Pyro Server')
    service_instance = load_module(service_class)(device_name=service_name)

    # TODO figure out if we really want multiplex.
    # Pyro5.config.SERVERTYPE = "multiplex"

    def start_service():
        # Locate the NS
        # NOTE: Moving this block outside start_service can lead to broken pipe errors
        try:
            nameserver = get_running_nameserver()
        except Exception as e:
            logger.warning(f"Pyro nameserver not running, can't create server. "
                           f"See 'huntsman-pyro nameserver' for details. {e!r}")
            return

        logger.info(f'Starting service_name={service_name} on host={host}:{port}')
        with PyroDaemon(host=host, port=port) as daemon:
            logger.info(f'Creating pyro daemon service for service_class={service_class}')
            uri = daemon.register(service_instance)
            logger.info(f'Registered {service_class} pyro daemon with uri={uri}'
                        f' and metadata={metadata}.')

            # Register service with the nameserver.
            nameserver.register(service_name, uri, safe=True, metadata=metadata)
            logger.info(f'Registered {service_class} with nameserver as {service_name}')

            # assert False
            # Save uri in the generic POCS config.
            # TODO do better checks if config-server is running rather than just a warning.
            try:
                set_config(f'pyro.devices.{service_name}.uri', uri)
            except Exception as e:
                logger.warning(f"Can't save {service_name} uri in config-server: {e!r}")

            try:
                logger.info(f'Pyro service {service_name} started. Ctrl-C/Cmd-C to quit...')
                daemon.requestLoop()
            except KeyboardInterrupt:
                logger.info(f'Pyro service {service_name} requested shutdown by user.')
            except Exception as e:  # noqa
                logger.info(f'{service_name} died unexpectedly: {e!r}')
            finally:
                logger.info(f'Shutting down {service_name} pyro server...')
                nameserver.remove(name=service_name)
                logger.info(f'Unregistered {service_name} from pyro nameserver')

    # Set up pyro service process.
    logger.info(f'Setting up Pyro service_name={service_name}.')
    service_process = Process(target=start_service)

    if auto_start:
        logger.info(f"Auto-starting new pyro service_name={service_name}")
        service_process.start()
        logger.success("Pyro nameserver started, blocking until finished...(Ctrl-c/Cmd-c to exit)")
        service_process.join()

    return service_process
