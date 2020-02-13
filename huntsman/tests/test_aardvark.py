# Named after an African nocturnal insectivore because for mysterious reasons these
# tests were failing if run towards the end of the test suite.
import logging

import pytest
import Pyro4
import Pyro4.errors
from astropy import units as u

from panoptes.utils import error

from huntsman.utils import get_own_ip


def test_get_own_ip():
    ip = get_own_ip()
    assert ip


def test_get_own_ip_verbose():
    ip = get_own_ip(verbose=True)
    assert ip


def test_get_own_ip_logger():
    logger = logging.getLogger()
    ip = get_own_ip(logger=logger)
    assert ip


def test_name_server(name_server):
    # Check that it's running.
    assert name_server.poll() is None


def test_locate_name_server(name_server):
    # Check that we can connect to the name server
    Pyro4.locateNS()


def test_test_server(test_server):
    # Check that it is running
    assert test_server.poll() is None


def test_quantity_argument(test_proxy):
    test_proxy.quantity_argument(550 * u.nm)
    test_proxy.quantity_argument(1.21 * u.GW)


def test_quantity_return(test_proxy):
    q = test_proxy.quantity_return()
    assert isinstance(q, u.Quantity)
    assert q == 42 * u.km * u.ng / u.Ms


def test_builtin_exception(test_proxy):
    with pytest.raises(RuntimeError):
        test_proxy.raise_runtimeerror()
    with pytest.raises(AssertionError):
        test_proxy.raise_assertionerror()


def test_pocs_exception(test_proxy):
    with pytest.raises(error.PanError):
        test_proxy.raise_panerror()


def test_pocs_subclass(test_proxy):
    with pytest.raises(error.Timeout):
        test_proxy.raise_timeout()
    with pytest.raises(error.NotSupported):
        test_proxy.raise_notsupported()
    with pytest.raises(error.IllegalValue):
        test_proxy.raise_illegalvalue()


def test_undeserialisable(test_proxy):
    with pytest.raises(Pyro4.errors.SerializeError):
        test_proxy.raise_undeserialisable()


def test_config_server(config_server):
    # Check we can get a config
    assert config_server.poll() is None


def test_camera_server(camera_server):
    # Check that it's running.
    assert camera_server.poll() is None


def test_camera_detection(camera_server):
    with Pyro4.locateNS() as ns:
        cameras = ns.list(metadata_all={'POCS', 'Camera'})
    # Should be one distributed camera, a simulator with simulated focuser
    assert len(cameras) == 1
