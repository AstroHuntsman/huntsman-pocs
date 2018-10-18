import os
import pytest
import signal
import subprocess
import time
import copy
from warnings import warn
import Pyro4

import pocs.base
from pocs.utils.config import load_config
from pocs.utils.database import PanDB

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
def config(images_dir):
    pocs.base.reset_global_config()

    global _one_time_config
    if not _one_time_config:
        _one_time_config = load_config(ignore_local=True, simulator=['all'])
        _one_time_config['db']['name'] = 'huntsman_testing'
        _one_time_config['name'] = 'PAN000'  # Make sure always testing with PAN000
        _one_time_config['scheduler']['fields_file'] = 'simulator.yaml'

    _one_time_config['directories']['images'] = images_dir

    return copy.deepcopy(_one_time_config)


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
