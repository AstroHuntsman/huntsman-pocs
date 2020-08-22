import os
import pytest
import signal
import subprocess
import time
import copy
import shutil
from warnings import warn
import Pyro4
import stat
import tempfile
from contextlib import suppress
import logging

from _pytest.logging import caplog as _caplog

from panoptes.pocs import hardware
from panoptes.utils.database import PanDB
from panoptes.utils.config.client import get_config
from panoptes.utils.config.client import set_config
from panoptes.utils.config.server import config_server

from huntsman.pocs.utils import load_config, get_own_ip
# This import is needed to set up the custom (de)serializers in the same scope
# as the pyro test server proxy creation.
from huntsman.pocs.utils import pyro as pyro_utils
from huntsman.pocs.utils.config import query_config_server

from panoptes.utils.logger import get_logger, PanLogger

_all_databases = ['file', 'memory']

LOGGER_INFO = PanLogger()

logger = get_logger()
logger.enable('panoptes')
logger.level("testing", no=15, icon="🤖", color="<YELLOW><black>")
log_file_path = os.path.join(
    os.getenv('PANLOG', '/var/panoptes/logs'),
    'panoptes-testing.log'
)
startup_message = ' STARTING NEW PYTEST RUN '
logger.add(log_file_path,
           enqueue=True,  # multiprocessing
           colorize=True,
           backtrace=True,
           diagnose=True,
           catch=True,
           # Start new log file for each testing run.
           rotation=lambda msg, _: startup_message in msg,
           level='TRACE')
logger.log('testing', '*' * 25 + startup_message + '*' * 25)
# Make the log file world readable.
os.chmod(log_file_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)


def pytest_addoption(parser):
    hw_names = ",".join(hardware.get_all_names()) + ' (or all for all hardware)'
    db_names = ",".join(_all_databases) + ' (or all for all databases)'
    group = parser.getgroup("PANOPTES pytest options")
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


@pytest.fixture(scope='module')
def images_dir_control(tmpdir_factory):
    directory = tmpdir_factory.mktemp('images')
    return str(directory)


@pytest.fixture(scope='module')
def images_dir_device(tmpdir_factory):
    directory = tmpdir_factory.mktemp('images_local')
    return str(directory)


@pytest.fixture(scope="session")
def db_name():
    return 'huntsman_testing'


def end_process(proc):
    """
    Makes absolutely sure that a process is definitely well and truly dead.

    Args:
        proc (subprocess.Popen): Popen object for the process
    """
    expected_return = 0
    if proc.poll() is None:
        # I'm not dead!
        expected_return = -signal.SIGINT
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            warn("Timeout waiting for {} to exit!".format(proc.pid))
            if proc.poll() is None:
                # I'm getting better!
                warn("Sending SIGTERM to {}...".format(proc.pid))
                expected_return = -signal.SIGTERM
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    warn("Timeout waiting for {} to terminate!".format(proc.pid))
                    if proc.poll() is None:
                        # I feel fine!
                        warn("Sending SIGKILL to {}...".format(proc.pid))
                        expected_return = -signal.SIGKILL
                        proc.kill()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired as err:
                            warn("Timeout waiting for {} to die! Giving up".format(proc.pid))
                            raise err
    else:
        warn("Process {} already exited!".format(proc.pid))

    if proc.returncode != expected_return:
        warn("Expected return code {} from {}, got {}!".format(expected_return,
                                                               proc.pid,
                                                               proc.returncode))
    return proc.returncode


@pytest.fixture(scope='session')
def name_server(request):
    ns_cmds = [os.path.expandvars('$HUNTSMAN_POCS/scripts/pyro_name_server.py'),
               '--host', 'localhost']
    ns_proc = subprocess.Popen(ns_cmds)
    request.addfinalizer(lambda: end_process(ns_proc))
    # Give name server time to start up
    waited = 0
    while waited <= 20:
        try:
            Pyro4.locateNS(host='localhost')
        except Pyro4.errors.NamingError:
            time.sleep(1)
            waited += 1
        else:
            return ns_proc

    raise TimeoutError("Timeout waiting for name server to start")


@pytest.fixture(scope='module')
def config_server(name_server, request, images_dir_control, images_dir_device):
    """
    The annoyance of this is that the test code may have a different IP
    from those in the actual device_info.yaml and can vary between runtime
    environments. So, here is a hack to make it work.
    """
    # Start the config server
    cmd = [os.path.expandvars(
        '$HUNTSMAN_POCS/scripts/start_config_server.py')]
    proc = subprocess.Popen(cmd)
    request.addfinalizer(lambda: end_process(proc))

    # Check the config server works
    waited = 0
    while waited <= 20:
        try:

            config = query_config_server()
            assert (isinstance(config, dict))

            # Add an entry for the IP used by the test machine
            config_server = Pyro4.Proxy('PYRONAME:config_server')
            key = get_own_ip()
            config = config_server.config
            config[key] = config['localhost']

            # Modify some additional entries to facilitate tests
            config[key]['directories']['images'] = images_dir_device
            config['control']['directories']['images'] = images_dir_control

            # Update the config in the config server
            config_server.config = config

            return proc

        except Exception:
            time.sleep(1)
            waited += 1

    raise TimeoutError("Timeout waiting for config server.")


@pytest.fixture(scope='module')
def camera_server(name_server, config_server, request):
    cs_cmds = [os.path.expandvars('$HUNTSMAN_POCS/scripts/pyro_camera_server.py'),
               '--ignore_local']
    cs_proc = subprocess.Popen(cs_cmds)
    request.addfinalizer(lambda: end_process(cs_proc))
    # Give camera server time to start up
    waited = 0
    while waited <= 20:
        with Pyro4.locateNS(host='localhost') as ns:
            cameras = ns.list(metadata_all={'POCS', 'Camera'})
        if len(cameras) == 1:
            return cs_proc
        time.sleep(1)
        waited += 1

    raise TimeoutError("Timeout waiting for camera server to start")


@pytest.fixture(scope='module')
def test_server(name_server, request):
    cs_cmds = [os.path.expandvars('$HUNTSMAN_POCS/scripts/pyro_test_server.py'), ]
    cs_proc = subprocess.Popen(cs_cmds)
    request.addfinalizer(lambda: end_process(cs_proc))
    # Give test server time to start up
    waited = 0
    while waited <= 20:
        with Pyro4.locateNS(host='localhost') as ns:
            test_servers = ns.list(metadata_all={'POCS', 'Test'})
        if len(test_servers) == 1:
            return cs_proc
        time.sleep(1)
        waited += 1

    raise TimeoutError("Timeout waiting for camera server to start")


@pytest.fixture(scope='module')
def test_proxy(test_server):
    proxy = Pyro4.Proxy("PYRONAME:test_server")
    return proxy


@pytest.fixture(scope='session')
def config_path():
    return os.path.expandvars('${HUNTSMAN_POCS}/tests/pocs_testing.yaml')


@pytest.fixture(scope='module', autouse=True)
def static_config_server(config_path, images_dir, db_name):
    logger.log('testing', f'Starting static_config_server for testing session')

    proc = config_server(
        config_path,
        ignore_local=True,
        auto_save=False
    )

    logger.log('testing', f'static_config_server started with {proc.pid=}')

    # Give server time to start
    while get_config('name') is None:  # pragma: no cover
        logger.log('testing', f'Waiting for static_config_server {proc.pid=}, sleeping 1 second.')
        time.sleep(1)

    set_config('directories.images', images_dir)

    logger.log('testing', f'Startup config_server name=[{get_config("name")}]')
    yield
    logger.log('testing', f'Killing static_config_server started with PID={proc.pid}')
    proc.terminate()


@pytest.fixture
def temp_file(tmp_path):
    d = tmp_path
    d.mkdir(exist_ok=True)
    f = d / 'temp'
    yield f
    f.unlink(missing_ok=True)


@pytest.fixture(scope='session')
def images_dir(tmpdir_factory):
    directory = tmpdir_factory.mktemp('images')
    return str(directory)


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


@pytest.fixture(scope='function')
def memory_db(db_name):
    PanDB.permanently_erase_database('memory', db_name, really='Yes', dangerous='Totally')
    return PanDB(db_type='memory', db_name=db_name)


@pytest.fixture(scope='session')
def data_dir():
    return os.path.expandvars('${POCS}/tests/data')


@pytest.fixture(scope='function')
def unsolved_fits_file(data_dir):
    orig_file = os.path.join(data_dir, 'unsolved.fits')

    with tempfile.TemporaryDirectory() as tmpdirname:
        copy_file = shutil.copy2(orig_file, tmpdirname)
        yield copy_file


@pytest.fixture(scope='function')
def solved_fits_file(data_dir):
    orig_file = os.path.join(data_dir, 'solved.fits.fz')

    with tempfile.TemporaryDirectory() as tmpdirname:
        copy_file = shutil.copy2(orig_file, tmpdirname)
        yield copy_file


@pytest.fixture(scope='function')
def tiny_fits_file(data_dir):
    orig_file = os.path.join(data_dir, 'tiny.fits')

    with tempfile.TemporaryDirectory() as tmpdirname:
        copy_file = shutil.copy2(orig_file, tmpdirname)
        yield copy_file


@pytest.fixture(scope='function')
def noheader_fits_file(data_dir):
    orig_file = os.path.join(data_dir, 'noheader.fits')

    with tempfile.TemporaryDirectory() as tmpdirname:
        copy_file = shutil.copy2(orig_file, tmpdirname)
        yield copy_file


@pytest.fixture(scope='function')
def cr2_file(data_dir):
    cr2_path = os.path.join(data_dir, 'canon.cr2')

    if not os.path.exists(cr2_path):
        pytest.skip("No CR2 file found, skipping test.")

    return cr2_path


@pytest.fixture()
def caplog(_caplog):
    class PropagatedHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(PropagatedHandler(), format="{message}")
    yield _caplog
    with suppress(ValueError):
        logger.remove(handler_id)
