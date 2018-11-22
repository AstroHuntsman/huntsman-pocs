import os
import pytest
import signal
import subprocess
import time
import copy
from warnings import warn
import Pyro4

import pocs.base
from pocs.utils.logger import get_root_logger
from pocs.utils.database import PanDB
from pocs.utils.messaging import PanMessaging

from huntsman.utils import load_config

# Global variable with the default config; we read it once, copy it each time it is needed.
_one_time_config = None


def pytest_addoption(parser):
    parser.addoption(
        "--hardware-test",
        action="store_true",
        default=False,
        help="Test with hardware attached")
    parser.addoption(
        "--camera",
        action="store_true",
        default=False,
        help="If a real camera attached")
    parser.addoption("--mount", action="store_true", default=False,
                     help="If a real mount attached")
    parser.addoption(
        "--weather",
        action="store_true",
        default=False,
        help="If a real weather station attached")
    parser.addoption("--solve", action="store_true", default=False,
                     help="If tests that require solving should be run")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware-test"):
        # --hardware-test given in cli: do not skip harware tests
        return
    skip_hardware = pytest.mark.skip(reason="need --hardware-test option to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)


@pytest.fixture(scope='module')
def images_dir(tmpdir_factory):
    directory = tmpdir_factory.mktemp('images')
    return str(directory)


@pytest.fixture(scope='function')
def config(images_dir, messaging_ports):
    pocs.base.reset_global_config()

    global _one_time_config
    if not _one_time_config:
        _one_time_config = load_config(ignore_local=True, simulator=['all'])
        _one_time_config['db']['name'] = 'huntsman_testing'
        _one_time_config['name'] = 'HuntsmanTest'
        _one_time_config['scheduler']['fields_file'] = 'simulator.yaml'
        _one_time_config['scheduler']['check_file'] = False

    # Make a copy before we modify based on test fixtures.
    result = copy.deepcopy(_one_time_config)

    # We allow for each test to have its own images directory, and thus
    # to not conflict with each other.
    result['directories']['images'] = images_dir

    # For now (October 2018), POCS assumes that the pub and sub ports are
    # sequential. Make sure that is what the test fixtures have in them.
    # TODO(jamessynge): Remove this once pocs.yaml (or messaging.yaml?) explicitly
    # lists the ports to be used.
    assert messaging_ports['cmd_ports'][0] == (messaging_ports['cmd_ports'][1] - 1)
    assert messaging_ports['msg_ports'][0] == (messaging_ports['msg_ports'][1] - 1)

    # We don't want to use the same production messaging ports, just in case
    # these tests are running on a working scope.
    try:
        result['messaging']['cmd_port'] = messaging_ports['cmd_ports'][0]
        result['messaging']['msg_port'] = messaging_ports['msg_ports'][0]
    except KeyError:
        pass

    get_root_logger().debug('config fixture: {!r}', result)
    return result


@pytest.fixture
def db():
    return PanDB()


@pytest.fixture
def data_dir():
    return '{}/pocs/tests/data'.format(os.getenv('POCS'))


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
        except subprocess.TimeoutExpired as err:
            warn("Timeout waiting for {} to exit!".format(proc.pid))
            if proc.poll() is None:
                # I'm getting better!
                warn("Sending SIGTERM to {}...".format(proc.pid))
                expected_return = -signal.SIGTERM
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired as err:
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


@pytest.fixture(scope='session')
def camera_server(name_server, request):
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

# -----------------------------------------------------------------------
# Messaging support fixtures. It is important that tests NOT use the same
# ports that the real pocs_shell et al use; when they use the same ports,
# then tests may cause errors in the real system (e.g. by sending a
# shutdown command).


@pytest.fixture(scope='module')
def messaging_ports():
    # Some code (e.g. POCS._setup_messaging) assumes that sub and pub ports
    # are sequential so these need to match that assumption for now.
    return dict(msg_ports=(43001, 43002), cmd_ports=(44001, 44002))


@pytest.fixture(scope='function')
def message_forwarder(messaging_ports):
    cmd = os.path.join(os.getenv('POCS'), 'scripts', 'run_messaging_hub.py')
    args = [cmd]
    # Note that the other programs using these port pairs consider
    # them to be pub and sub, in that order, but the forwarder sees things
    # in reverse: it subscribes to the port that others publish to,
    # and it publishes to the port that others subscribe to.
    for _, (sub, pub) in messaging_ports.items():
        args.append('--pair')
        args.append(str(sub))
        args.append(str(pub))

    get_root_logger().info('message_forwarder fixture starting: {}', args)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # It takes a while for the forwarder to start, so allow for that.
    # TODO(jamessynge): Come up with a way to speed up these fixtures.
    time.sleep(3)
    yield messaging_ports
    proc.terminate()


@pytest.fixture(scope='function')
def msg_publisher(message_forwarder):
    port = message_forwarder['msg_ports'][0]
    publisher = PanMessaging.create_publisher(port)
    yield publisher
    publisher.close()


@pytest.fixture(scope='function')
def msg_subscriber(message_forwarder):
    port = message_forwarder['msg_ports'][1]
    subscriber = PanMessaging.create_subscriber(port)
    yield subscriber
    subscriber.close()


@pytest.fixture(scope='function')
def cmd_publisher(message_forwarder):
    port = message_forwarder['cmd_ports'][0]
    publisher = PanMessaging.create_publisher(port)
    yield publisher
    publisher.close()


@pytest.fixture(scope='function')
def cmd_subscriber(message_forwarder):
    port = message_forwarder['cmd_ports'][1]
    subscriber = PanMessaging.create_subscriber(port)
    yield subscriber
    subscriber.close()
