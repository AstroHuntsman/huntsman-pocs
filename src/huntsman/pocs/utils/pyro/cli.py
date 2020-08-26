import click

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.server import run_nameserver
from huntsman.pocs.utils.pyro.server import run_pyro_service
from panoptes.utils.library import load_module


@click.group()
@click.option('--verbose/--no-verbose', help='Turn on logger for panoptes utils, default False')
def command(verbose=False):
    if verbose:
        logger.enable('panoptes')


@click.command('nameserver')
@click.option('--host', default=None, help='The config server IP address or host name. '
                                           'If None, lookup in config-server, else default localhost.')
@click.option('--port', default=None, help='The config server port. If None, lookup in config-server, else '
                                           'default 0 for auto-assign.')
@click.option('--autoclean', default=0, help='Interval in seconds to perform automatic object cleanup, '
                                             'default 0 for no autocleaning.')
def nameserver(host=None, port=None, autoclean=0):
    """Starts the pyro name server.

    This function is registered as an entry_point for the module and should be called from
    the command line accordingly.
    """

    try:
        run_nameserver(host=host, port=port, autoclean=autoclean)
    except KeyboardInterrupt:
        logger.info(f'Pyro nameserver interrupted, shutting down.')
    except Exception as e:  # noqa
        logger.error(f'Pyro nameserver shutdown unexpectedly {e!r}')


@click.command('service')
@click.argument('service-name')
@click.option('--service-class', default=None, help='The class to register with Pyro. '
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
    # Look up the actual service class object.
    full_service_class = load_module(service_class)

    run_pyro_service(service_name=service_name, service_class=full_service_class, host=host, port=port)


command.add_command(nameserver)
command.add_command(service)
