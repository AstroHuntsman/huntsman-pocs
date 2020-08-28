import click

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.nameserver import pyro_nameserver
from huntsman.pocs.utils.pyro.service import pyro_service


@click.group()
@click.option('--verbose/--no-verbose', help='Turn on logger for panoptes utils, default False')
def entry_point(verbose=False):
    if verbose:
        logger.enable('panoptes')


@click.command('nameserver')
@click.option('--host', default=None, help='The config server IP address or host name. '
                                           'If None, lookup in config-server, else default localhost.')
@click.option('--port', default=None, help='The config server port. If None, lookup in config-server, else '
                                           'default 0 for auto-assign.')
@click.option('--auto-clean', default=0, help='Interval in seconds to perform automatic object cleanup, '
                                              'default 0 for no auto_cleaning.')
def nameserver(host=None, port=None, auto_clean=0):
    """Starts the pyro name server.

    This function is registered as an entry_point for the module and should be called from
    the command line accordingly.
    """

    try:
        logger.info(f'Creating Pyro nameserver')
        ns_proc = pyro_nameserver(host=host, port=port, auto_clean=auto_clean, auto_start=False)
        logger.info(f'Starting Pyro nameserver from cli')
        ns_proc.start()
        logger.info(f'Pyro nameserver started. Ctrl-C/Cmd-C to quit...')
        ns_proc.join()
    except KeyboardInterrupt:
        logger.info(f'Pyro nameserver interrupted, shutting down.')
    except Exception as e:  # noqa
        logger.error(f'Pyro nameserver shutdown unexpectedly {e!r}')
    finally:
        logger.info(f'Pyro nameserver shut down.')


@click.command('service')
@click.argument('service-name')
@click.option('--service-class', required=True, default=None,
              help='The class to register with Pyro. '
                   'This should be the fully qualified namespace for the class, '
                   'e.g. huntsman.pocs.camera.pyro.CameraService.')
@click.option('--host', default=None, help='The config server IP address or host name. '
                                           'If None, lookup in config-server, else default localhost.')
@click.option('--port', default=None, help='The config server port. If None, lookup in config-server, else '
                                           'default 0 for auto-assign.')
def service(service_name, service_class=None, host=None, port=None):
    """Starts a pyro service.

    This function is registered as an entry_point for the module and should be called from
    the command line on a remote (to the control computer) device.
    """
    logger.info(f'Starting pyro service {service_name=} for {service_class=}')

    try:
        logger.info(f'Creating Pyro service {service_name}')

        service_proc = pyro_service(service_class=service_class,
                                    service_name=service_name,
                                    host=host,
                                    port=port,
                                    auto_start=False)
        logger.info(f'Starting Pyro service process {service_name} from cli')
        service_proc.start()
        service_proc.join()
    except (KeyboardInterrupt, StopIteration):
        logger.info(f'Pyro service {service_name} interrupted, shutting down.')
    except Exception as e:  # noqa
        logger.error(f'Pyro {service_name} shutdown unexpectedly {e!r}')
    finally:
        logger.info(f'Pyro {service_name} shut down.')


entry_point.add_command(nameserver)
entry_point.add_command(service)
