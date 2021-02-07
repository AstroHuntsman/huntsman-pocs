import logging
import os
import stat
import time
from contextlib import suppress

import pytest
from huntsman.pocs.utils.pyro.nameserver import pyro_nameserver
from panoptes.pocs import hardware
from panoptes.utils.database import PanDB
from panoptes.utils.config.client import get_config, set_config
from panoptes.utils.config.server import config_server
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.service import pyro_service_process
import huntsman.pocs.utils.pyro.serializers  # noqa

_all_databases = ['file', 'memory']

logger.enable('panoptes')
logger.level("testing", no=15, icon="🤖", color="<LIGHT-BLUE><black>")
log_fmt = "<lvl>{level:.1s}</lvl> " \
          "<light-blue>{time:MM-DD HH:mm:ss.ss!UTC}</>" \
          "<blue>({time:HH:mm:ss.ss})</> " \
          "| <c>{name} {function}:{line}</c> | " \
          "<lvl>{message}</lvl>"

# Put the log file in the tmp dir.
log_dir = os.getenv('PANLOG', 'logs')
log_file_path = os.path.join(log_dir, 'huntsman-testing.log')
startup_message = f' STARTING NEW PYTEST RUN - LOGS: {log_file_path} '
logger.add(log_file_path,
           enqueue=True,  # multiprocessing
           format=log_fmt,
           colorize=True,
           # TODO decide on these options
           backtrace=True,
           diagnose=True,
           catch=True,
           # Start new log file for each testing run.
           rotation=lambda msg, _: startup_message in msg,
           level='TRACE')
logger.log('testing', '*' * 25 + startup_message + '*' * 25)

# Make the log file world readable.
os.chmod(log_file_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)


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
    config_proc = config_server(config_file,
                                host=config_host,
                                port=config_port,
                                load_local=False,
                                save_local=False)
    logger.success(f'Config server set up: {config_proc!r}')

    while get_config(key='pyro.nameserver', host=config_host, port=config_port) is None:
        logger.info(f'Waiting for config server')
        time.sleep(1)

    nameserver_config = get_config(key='pyro.nameserver', host=config_host, port=config_port)
    service_config = get_config(key=f'pyro.{service_class}', host=config_host, port=config_port)

    # Start pyro nameserver
    logger.info(f'Starting nameserver with {nameserver_config!r}')
    ns_proc = pyro_nameserver(**nameserver_config)
    ns_proc.daemon = True
    ns_proc.start()
    logger.success(f'Pyro nameserver started: {ns_proc!r}')

    # Start a pyro camera service
    logger.info(f"Creating testing Pyro {service_class}")
    pyro_proc = pyro_service_process(
        service_class=f'huntsman.pocs.camera.pyro.service.{service_class}',
        service_name='dslr.00',
        **service_config,
    )
    pyro_proc.daemon = True
    pyro_proc.start()
    logger.success(f'Pyro service created: {pyro_proc!r}')


def pytest_addoption(parser):
    hw_names = ",".join(hardware.get_all_names()) + ' (or all for all hardware)'
    db_names = ",".join(_all_databases) + ' (or all for all databases)'
    group = parser.getgroup("Huntsman pytest options")
    group.addoption(
        "--with-hardware",
        nargs='+',
        default=[],
        help=f"A comma separated list of hardware to test. List items can include: {hw_names}")
    group.addoption(
        "--without-hardware",
        nargs='+',
        default=[],
        help=f"A comma separated list of hardware to NOT test.  List items can include: {hw_names}")
    group.addoption(
        "--test-databases",
        nargs="+",
        default=['file'],
        help=f"Test databases in the list. List items can include: {db_names}. Note that "
             f"travis-ci will test all of "
             f"them by default.")


def pytest_collection_modifyitems(config, items):
    """Modify tests to skip or not based on cli options.
    Certain tests should only be run when the appropriate hardware is attached.
    Other tests fail if real hardware is attached (e.g. they expect there is no
    hardware). The names of the types of hardware are in hardware.py, but
    include 'mount' and 'camera'. For a test that requires a mount, for
    example, the test should be marked as follows:
    `@pytest.mark.with_mount`
    And the same applies for the names of other types of hardware.
    For a test that requires that there be no cameras attached, mark the test
    as follows:
    `@pytest.mark.without_camera`
    """

    # without_hardware is a list of hardware names whose tests we don't want to run.
    without_hardware = hardware.get_simulator_names(
        simulator=config.getoption('--without-hardware'))

    # with_hardware is a list of hardware names for which we have that hardware attached.
    with_hardware = hardware.get_simulator_names(simulator=config.getoption('--with-hardware'))

    for name in without_hardware:
        # User does not want to run tests that interact with hardware called name,
        # whether it is marked as with_name or without_name.
        if name in with_hardware:
            print(f'Warning: {name} in both --with-hardware and --without-hardware')
            with_hardware.remove(name)
        skip = pytest.mark.skip(reason=f"--without-hardware={name} specified")
        with_keyword = f'with_{name}'
        without_keyword = f'without_{name}'
        for item in items:
            if with_keyword in item.keywords or without_keyword in item.keywords:
                item.add_marker(skip)

    for name in hardware.get_all_names(without=with_hardware):
        # We don't have hardware called name, so find all tests that need that
        # hardware and mark it to be skipped.
        skip = pytest.mark.skip(reason=f"Test needs --with-hardware={name} option to run")
        keyword = 'with_' + name
        for item in items:
            if keyword in item.keywords:
                item.add_marker(skip)


def pytest_runtest_logstart(nodeid, location):
    """Signal the start of running a single test item.
    This hook will be called before pytest_runtest_setup(),
    pytest_runtest_call() and pytest_runtest_teardown() hooks.
    Args:
        nodeid (str) – full id of the item
        location – a triple of (filename, linenum, testname)
    """
    with suppress(Exception):
        logger.log('testing', '##########' * 8)
        logger.log('testing', f'     START TEST {nodeid}')
        logger.log('testing', '')


def pytest_runtest_logfinish(nodeid, location):
    """Signal the complete finish of running a single test item.
    This hook will be called after pytest_runtest_setup(),
    pytest_runtest_call() and pytest_runtest_teardown() hooks.
    Args:
        nodeid (str) – full id of the item
        location – a triple of (filename, linenum, testname)
    """
    with suppress(Exception):
        logger.log('testing', '')
        logger.log('testing', f'       END TEST {nodeid}')
        logger.log('testing', '##########' * 8)


def pytest_runtest_logreport(report):
    """Adds the failure info that pytest prints to stdout into the log."""
    if report.skipped or report.outcome != 'failed':
        return
    with suppress(Exception):
        logger.log('testing', '')
        logger.log('testing',
                   f'  TEST {report.nodeid} FAILED during {report.when} {report.longreprtext} ')
        if report.capstdout:
            logger.log('testing',
                       f'============ Captured stdout during {report.when} {report.capstdout} '
                       f'============')
        if report.capstderr:
            logger.log('testing',
                       f'============ Captured stdout during {report.when} {report.capstderr} '
                       f'============')


@pytest.fixture(scope='session')
def base_dir():
    return os.getenv('HUNTSMAN_POCS', '/var/huntsman/huntsman-pocs')


@pytest.fixture(scope="session")
def db_name():
    return 'huntsman_testing'


@pytest.fixture(scope='session')
def config_path(base_dir):
    return os.path.expandvars(f'{base_dir}/testing/testing.yaml')


@pytest.fixture
def temp_file(tmp_path):
    d = tmp_path
    d.mkdir(exist_ok=True)
    f = d / 'temp'
    yield f
    f.unlink(missing_ok=True)


@pytest.fixture(scope='module')
def images_dir(tmpdir_factory):
    directory = str(tmpdir_factory.mktemp('images'))
    set_config("directories.images", directory)
    return directory


@pytest.fixture(scope='function', params=_all_databases)
def db_type(request, db_name):
    db_list = request.config.option.test_databases
    if request.param not in db_list and 'all' not in db_list:
        pytest.skip(f"Skipping {request.param} DB, set --test-all-databases=True")

    PanDB.permanently_erase_database(request.param, db_name, really='Yes', dangerous='Totally')
    return request.param


@pytest.fixture(scope='function')
def db(db_type, db_name):
    return PanDB(db_type=db_type, db_name=db_name, connect=True)


@pytest.fixture()
def caplog(_caplog):
    class PropagatedHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(PropagatedHandler(), format="{message}")
    yield _caplog
    with suppress(ValueError):
        logger.remove(handler_id)


@pytest.fixture(scope='module')
def camera_service_name():
    return 'dslr.00'
