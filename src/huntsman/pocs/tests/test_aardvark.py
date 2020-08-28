# Named after an African nocturnal insectivore because for mysterious reasons these
# tests were failing if run towards the end of the test suite.

import pytest
import Pyro4
import Pyro4.errors
from astropy import units as u

from panoptes.utils import error


def test_name_server(pyro_nameserver):
    # Check that it's running.
    assert pyro_nameserver.poll() is None


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
