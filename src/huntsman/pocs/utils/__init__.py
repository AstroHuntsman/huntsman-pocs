import os
import netifaces
from pocs.utils import listify
from pocs.utils.config import load_config as config_loader

from pocs.mount import create_mount_from_config
from huntsman.pocs.scheduler import create_scheduler_from_config
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory


def load_config(config_files=None, **kwargs):
    '''

    '''
    config_dir = os.path.join(os.environ['HUNTSMAN_POCS'], 'conf_files')

    if config_files is None:
        config_files = ['huntsman.yaml']

    config_files = listify(config_files)
    config_files = [os.path.join(config_dir, config_file) for config_file in config_files]

    config = config_loader(config_files=config_files, **kwargs)
    return config


def create_huntsman_observatory(config=None, **kwargs):
    """
    Create a `HuntsmanObservatory` instance from a config.
    """
    if config is None:
        config = load_config()
    # Create cameras (may take a few minutes)
    cameras = create_cameras_from_config(config=config)
    # Create mount
    mount = create_mount_from_config(config=config)
    mount.initialize()
    # Create the scheduler
    scheduler = create_scheduler_from_config(config=config)
    # Create the observatory
    observatory = HuntsmanObservatory(cameras=cameras, mount=mount, scheduler=scheduler,
                                      **kwargs)
    return observatory


def get_own_ip(verbose=False, logger=None):
    """
    Attempts to automatically determine the IP address of the computer that it was run on.

    Args:
        verbose (bool, optional): If True print messages to standard output. Default false.
        logger (logging.Logger, optional): If given will log debug messages to the logger.

    Returns:
        host (str): IP address of the computer.

    Notes:
        This will probably return a useful value in most cases, however a computer can have
        several, equally valid IP addresses and it is not always possible to automatically
        determine the most appropriate one for the situation. This function simply looks for
        the default gateway, gets the IP addresses for the same interface as the default
        gateway, and returns the IP address that's in the same subnet as the gateway.
    """
    msg = 'Attempting to automatically determine IP address...'
    if verbose:
        print(msg)
    if logger:
        logger.debug(msg)
    # Hopefully there is a default gateway.
    default_gateway = netifaces.gateways()['default']
    # Get the gateway IP and associated inferface
    gateway_IP, interface = default_gateway[netifaces.AF_INET]
    msg = 'Found default gateway {} using interface {}'.format(gateway_IP, interface)
    if verbose:
        print(msg)
    if logger:
        logger.debug(msg)
    # Get the IP addresses from the interface
    addresses = []
    for address in netifaces.ifaddresses(interface)[netifaces.AF_INET]:
        addresses.append(address['addr'])
    # This will be a list with one or more entries. Probably want the one that starts
    # the same as the default gateway's IP.
    if len(addresses) > 1:
        msg = 'Interface has more than 1 IP address. Filtering on 1st byte...'
        if verbose:
            print(msg)
        if logger:
            logger.debug(msg)
        byte1, byte2 = gateway_IP.split('.')[0:2]
        addresses = [address for address in addresses if address.split('.')[0] == byte1]
        if len(addresses) > 1:
            msg = 'Interface still has more then 1 IP address. Filtering on 2nd byte...'
            if verbose:
                print(msg)
            if logger:
                logger.debug(msg)
            addresses = [address for address in addresses if address.split('.')[1] == byte2]

    assert len(addresses) == 1
    host = addresses[0]
    msg = 'Using IP address {} on interface {}'.format(addresses[0], interface)
    if verbose:
        print(msg)
    if logger:
        logger.debug(msg)
    return host


class DummyLogger():
    '''

    '''

    def __init__(self):
        pass

    def warning(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)

    def debug(self, msg):
        print(msg)

    def info(self, msg):
        print(msg)
