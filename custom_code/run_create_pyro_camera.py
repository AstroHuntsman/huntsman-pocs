import logging
import os
import stat
import time
from contextlib import suppress

import huntsman.pocs.utils.pyro.serializers  # noqa
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.nameserver import pyro_nameserver
from huntsman.pocs.utils.pyro.service import pyro_service_process
from panoptes.pocs import hardware
from panoptes.utils.config.client import get_config, set_config
from panoptes.utils.config.server import config_server
from panoptes.utils.database import PanDB


def pytest_configure(config):
    """Set up the testing."""
    logger.info('Setting up the config server.')
    config_file = 'tests/testing.yaml'

    config_host = 'localhost'
    config_port = '8765'
    service_class = 'CameraService'

    os.environ['PANOPTES_CONFIG_HOST'] = config_host
    os.environ['PANOPTES_CONFIG_PORT'] = config_port

    logger.info(f'Starting config-server for testing: {config_host=} {config_port=}')
    config_proc = config_server(
        config_file,
        host=config_host,
        port=config_port,
        load_local=False,
        save_local=False,
    )
    logger.success(f'Config server set up: {config_proc!r}')

    while get_config(key='pyro.nameserver', host=config_host, port=config_port) is None:
        logger.info(f'Waiting for config server')
        time.sleep(1)

    nameserver_config = get_config(
        key='pyro.nameserver', host=config_host, port=config_port
    )
    service_config = get_config(
        key=f'pyro.{service_class}', host=config_host, port=config_port
    )

    # Start pyro nameserver
    logger.info(f'Starting nameserver with {nameserver_config!r}')
    ns_proc = pyro_nameserver(**nameserver_config)
    ns_proc.daemon = True
    ns_proc.start()
    logger.success(f'Pyro nameserver started: {ns_proc!r}')

    # Start first pyro camera service
    logger.info(f"Creating first testing Pyro {service_class}")
    pyro_proc_00 = pyro_service_process(
        service_class=f'huntsman.pocs.camera.pyro.service.{service_class}',
        service_name='dslr.00',
        **service_config,
    )
    pyro_proc_00.daemon = True
    pyro_proc_00.start()
    logger.success(f'Pyro service created: {pyro_proc_00!r}')

    # Start second pyro camera service
    # logger.info(f"Creating second testing Pyro {service_class}")
    # pyro_proc_01 = pyro_service_process(
    #     service_class=f'huntsman.pocs.camera.pyro.service.{service_class}',
    #     service_name='dslr.01',
    #     **service_config,
    # )
    # pyro_proc_01.daemon = True
    # pyro_proc_01.start()
    # logger.success(f'Pyro service created: {pyro_proc_01!r}')


if __name__ == "__main__":
    config = None
    pytest_configure(config)
