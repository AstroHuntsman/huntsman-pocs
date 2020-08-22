import os
import netifaces
from panoptes.utils import listify
from panoptes.utils.config.helpers import load_config as config_loader

from huntsman.pocs.utils.logger import logger


def load_config(config_files=None, **kwargs):
    """

    """
    config_dir = os.path.join(os.environ['HUNTSMAN_POCS'], 'conf_files')

    if config_files is None:
        config_files = ['huntsman.yaml']

    config_files = listify(config_files)
    config_files = [os.path.join(config_dir, config_file) for config_file in config_files]

    config = config_loader(config_files=config_files, **kwargs)
    return config


def get_own_ip(verbose=False):
    """
    Attempts to automatically determine the IP address of the computer that it was run on.

    Args:
        verbose (bool, optional): If True print messages to standard output. Default false.

    Returns:
        host (str): IP address of the computer.

    Notes:
        This will probably return a useful value in most cases, however a computer can have
        several, equally valid IP addresses and it is not always possible to automatically
        determine the most appropriate one for the situation. This function simply looks for
        the default gateway, gets the IP addresses for the same interface as the default
        gateway, and returns the IP address that's in the same subnet as the gateway.
    """
    logger.debug('Attempting to automatically determine IP address...')

    # Hopefully there is a default gateway.
    default_gateway = netifaces.gateways()['default']
    # Get the gateway IP and associated interface.
    gateway_ip, interface = default_gateway[netifaces.AF_INET]
    logger.debug(f'Found default gateway {gateway_ip} using interface {interface}')

    # Get the IP addresses from the interface
    addresses = [address['addr'] for address in netifaces.ifaddresses(interface)[netifaces.AF_INET]]

    # This will be a list with one or more entries. Probably want the one that starts
    # the same as the default gateway's IP.
    if len(addresses) > 1:
        gateway_byte1, gateway_byte2 = gateway_ip.split('.')[0:2]
        logger.debug(f'Interface has more than 1 IP address. Filtering on 1st byte [{gateway_byte1}]...')
        addresses = [address for address in addresses if address.split('.')[0] == gateway_byte1]
        if len(addresses) > 1:
            logger.debug(f'Interface still has more than 1 IP address. Filtering on 2nd byte [{gateway_byte2}]...')
            addresses = [address for address in addresses if address.split('.')[1] == gateway_byte2]

    assert len(addresses) == 1
    host = addresses[0]

    logger.success(f'Using IP address {host} on interface {interface}')
    return host
