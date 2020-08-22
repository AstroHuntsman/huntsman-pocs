import sys
import time
import Pyro4
from panoptes.utils import current_time
from panoptes.utils.config import _parse_config
from huntsman.pocs.utils import load_config, get_own_ip, DummyLogger


@Pyro4.expose
class ConfigServer():

    def __init__(self, config_file=None, parse=True, refresh_interval=120,
                 **kwargs):
        """
        Parameters
        ----------
        config_file (str):
            The name of the config file to use. Default is device_info.yaml.
        parse (bool):
            Parse the config? Default True.
        refresh_interval (float):
            Frequency that the config is updated from file in seconds. Default 120s.
        """
        self._parse = parse
        self._refresh_interval = refresh_interval

        if config_file is None:
            config_file = 'device_info.yaml'

        # Read the config file
        self._config_kwargs = dict(config_files=[config_file], parse=self._parse,
                                   **kwargs)
        self._load_config()

    def _load_config(self):
        """
        Load the config from file.
        """
        self._config = load_config(**self._config_kwargs)
        self._last_refresh_time = current_time()

    @property
    def config(self):
        if current_time() - self._last_refresh_time > self._refresh_interval:
            self._load_config()
        return self._config

    @config.setter
    def config(self, config):
        self._config = config

    def get_config(self, key=None):
        """
        Retrieve the config file.
        """
        config = self.config

        if key is not None:
            config = config[key]

            # Need to run _parse_config if querying by key, as load_config
            # only checks top-level keys.
            if self._parse:
                config = _parse_config(config)

        return config


def locate_name_server(wait=None, logger=None):
    """
    Locate and return the name server (NS), waiting if necessary.

    Parameters
    ----------
    wait (float or None) [seconds]:
        If not None, attempt to locate the NS at this frequency.

    Returns
    -------
    Pyro name server.
    """
    if logger is None:
        logger = DummyLogger()
    if wait is None:
        return Pyro4.locateNS()

    try:
        # Look for NS periodically until it is found
        while True:
            try:
                return Pyro4.locateNS()
            except Pyro4.errors.PyroError:
                logger.info('Unable to locate name server. Waiting...')
                time.sleep(wait)

    # Catch keyboard interrupt
    except KeyboardInterrupt:
        logger.debug('Keyboard interrupt while locating name server.\
                     Terminating!')
        sys.exit(0)


def start_config_server(host=None, port=6563, name='config_server',
                        wait=120, logger=None, *args, **kwargs):
    """
    Start the config server by creating a ConfigServer instance and registering
    it with the Pyro name server.

    Parameters
    ----------
    host (str):
        The host name or IP address. If none, uses the IP of the local machine.
    port (int):
        The port with which to expose the server.
    name (str):
        The name of the config server used by the Pyro name server.
    wait (float or None) [seconds]:
        If not None, attempt to locate the NS at this frequency.
    """
    if logger is None:
        logger = DummyLogger()

    if host is None:
        host = get_own_ip()

    with Pyro4.Daemon(host=host, port=port) as daemon:

        # Locate the name server
        name_server = locate_name_server(wait=wait)
        logger.info('Found name server.')

        # Create a ConfigServer object
        config_server = ConfigServer(*args, **kwargs)

        # Register with pyro & the name server
        uri = daemon.register(config_server)
        name_server.register(name, uri)
        logger.info(f'ConfigServer object registered as: {uri}')

        # Request loop
        try:
            logger.info('Entering request loop... ')
            daemon.requestLoop()
        finally:
            logger.info('Unregistering from name server...')
            name_server.remove(name=name)


def query_config_server(key=None, name='config_server', logger=None, wait=None):
    """
    Query the config server.

    Parameters
    ----------
    key (str):
        The key used to query the config file. If none, the whole config is
        returned.
    name (str):
        The name used to locate the config server from the Pyro name server.
    wait (float or None) [seconds]:
        If not None, attempt to locate the NS at this frequency.

    Returns
    -------
    dict:
        The config dictionary.
    """
    if logger is None:
        logger = DummyLogger()

    while True:

        try:
            config_server = Pyro4.Proxy(f'PYRONAME:{name}')
            return config_server.get_config(key=key)

        except Pyro4.errors.NamingError as e:

            if wait is not None:
                logger.info(f'Failed to locate config server. \
                            Waiting {wait}s before retrying.')
                time.sleep(wait)
            else:
                logger.error('Failed to locate config server!')
                raise (e)

        except Exception as e:
            logger.error(f'Unable to load remote config: {e}')
            raise (e)


def load_device_config(key=None, config_files=None, logger=None, wait=None,
                       **kwargs):
    """
    Load the device config from either the config server or local files.

    Parameters
    ----------
    key:
        The key used to query the config server. Only used if config_files
        is None. If None, use the IP of the current device.
    config_files:
        List of config file names. If None (default), use the config server.
    wait (float or None) [seconds]:
        If not None, attempt to locate the NS at this frequency.

    Returns
    -------
    dict:
        The config dictionary.
    """
    if logger is None:
        logger = DummyLogger()

    # Load config from local files?
    if config_files is not None:
        logger.debug(f'Loading config from local file(s).')
        if key is None:
            try:
                config = load_config(config_files, **kwargs)[get_own_ip()]
            except KeyError:
                # Should only get to this fallback when doing local testing with simulated
                # camera and default config files.
                logger.warning("No config for own IP address, falling back to localhost.")
                config = load_config(config_files, **kwargs)['localhost']
        else:
            config = load_config(config_files, **kwargs)[key]

    # Load config from the config server?
    else:
        if key is None:
            try:
                my_ip = get_own_ip()
                logger.debug(f'Loading remote config for own IP: {my_ip}')
                config = query_config_server(key=my_ip, logger=logger, wait=wait)
            except KeyError:
                # Should only get to this fallback when doing local testing with simulated
                # camera and default config files.
                logger.warning("No config for own IP address, falling back to localhost.")
                config = query_config_server(key='localhost', logger=logger, wait=wait)
        else:
            logger.debug(f'Loading remote config with key: {key}')
            config = query_config_server(key=key, logger=logger, wait=wait)

    return config
