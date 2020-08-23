import sys

import astropy.units as u
import Pyro4
from Pyro4 import errors

from panoptes.utils import error

# This import is needed to set up the custom (de)serializers in the same scope
# as the TestServer.
from huntsman.pocs.utils.pyro import serializers
from huntsman.pocs.utils import get_own_ip
from huntsman.pocs.utils.logger import logger


class NewError(Exception):
    pass


@Pyro4.expose
class TestServer(object):

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


def run_test_server():
    """
    Runs a Pyro test server.
    """
    host = get_own_ip()

    with Pyro4.Daemon(host=host) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            logger.error('Failed to locate Pyro name server: {}'.format(err))
            sys.exit(1)

        logger.info('Found Pyro name server.')
        uri = daemon.register(TestServer)
        logger.info('Test server registered with daemon as {}'.format(uri))
        name_server.register('test_server', uri, metadata={"POCS", "Test"})
        logger.info('Registered with name server as test_server')
        logger.info('Starting request loop... (Control-C/Command-C to exit)')

        try:
            daemon.requestLoop()
        finally:
            logger.info('\nShutting down...')
            name_server.remove(name='test_server')
            logger.info('Unregistered from name server')
