import Pyro4
from Pyro4 import errors, naming

from huntsman.pocs.utils import get_own_ip
from huntsman.pocs.utils.logger import logger


def run_name_server(host=None, port=None, autoclean=0):
    """
    Runs a Pyro name server.

    The name server must be running in order to use distributed cameras with POCS. The name server
    should be started before starting camera servers or POCS.

    Args:
        host (str, optional): hostname/IP address to bind the name server to. If not given then
            get_own_ip will be used to attempt to automatically determine the IP addresses of
            the computer that the name server is being started on.
        port (int, optional): port number to bind the name server to. If not given then the port
            will be selected automatically (usually 9090).
        autoclean (int, optional): interval, in seconds, for automatic deregistration of objects
            from the name server if they cannot be connected. If not given no autocleaning will
            be done.
    """
    try:
        # Check that there isn't a name server already running
        name_server = Pyro4.locateNS()
    except errors.NamingError:
        if not host:
            # Not given an hostname or IP address. Will attempt to work it out.
            host = get_own_ip()
        else:
            host = str(host)

        if port is not None:
            port = int(port)

        Pyro4.config.NS_AUTOCLEAN = float(autoclean)

        logger.info("Starting Pyro name server... (Control-C/Command-C to exit)")
        naming.startNSloop(host=host, port=port)
    else:
        logger.info(f"Pyro name server {name_server} already running! Exiting...")
