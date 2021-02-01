import Pyro5.server
import astropy.units as u
from panoptes.utils import error


class NewError(Exception):
    pass


@Pyro5.server.expose
class TestService(object):

    def quantity_argument(self, q):
        assert isinstance(q, u.Quantity)

    def quantity_return(self):
        return 42 * u.km * u.ng / u.Ms

    def raise_runtimeerror(self):
        raise RuntimeError("This is a test RuntimeError.")

    def raise_assertionerror(self):
        assert False

    def raise_panerror(self):
        raise error.PanError("This is a test PanError.")

    def raise_timeout(self):
        raise error.Timeout("This is a test Timeout.")

    def raise_notsupported(self):
        raise error.NotSupported("This is a test NotSupported.")

    def raise_illegalvalue(self):
        raise error.IllegalValue("This is a test IllegalValue.")

    def raise_undeserialisable(self):
        raise NewError("Pyro can't de-serialise this.")
