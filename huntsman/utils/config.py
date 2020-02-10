#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan  2 12:04:11 2020

@author: danjampro

Code to provide a config server using pyro.
"""
import os, sys, time
import Pyro4
from huntsman.utils import load_config, get_own_ip, DummyLogger
from pocs.utils.config import _parse_config

#==============================================================================

@Pyro4.expose
class ConfigServer():
    '''
    Class representing the config server.
    '''
    def __init__(self, config_file=None, parse=True, **kwargs):
        '''

        '''
        self.parse = parse

        #Read the config file(s)
        self._load_config(**kwargs)

    @property
    def config(self):
        return self.config_

    @config.setter
    def config(self, config):
        self.config_ = config


    def _load_config(self, device_kwargs={}, control_kwargs={}):
        '''
        Load the config files for devices and control.

        Parameters
        ----------
        device_kwargs (dict):
            Additional kwargs for device_config.

        control_kwargs (dict):
            Additional kwargs for control config.
        '''
        #Specify the device config files
        config_files = device_kwargs.pop('config_files', ['device_info.yaml'])

        #Load the device config
        self.config_ = load_config(parse=self.parse, config_files=config_files,
                                   **device_kwargs)

        #Also load the control config
        self.config_['control'] = load_config(parse=False, **control_kwargs)


    def get_config(self, key=None):
        '''
        Retrieve the config file.
        '''
        if key is None:
            return self.config

        # Need to run _parse_config if querying by key, as load_config
        # only checks top-level keys.
        if self.parse:
            config = _parse_config(self.config_[key])
        else:
            config = self.config_[key]

        return config

#==============================================================================

def locate_name_server(wait=None, logger=None):
    '''
    Locate and return the name server (NS), waiting if necessary.

    Parameters
    ----------
    wait (float or None) [seconds]:
        If not None, attempt to locate the NS at this frequency.

    Returns
    -------
    Pyro name server.
    '''
    if logger is None:
        logger = DummyLogger()
    if wait is None:
        return Pyro4.locateNS()

    try:
        #Look for NS periodically until it is found
        while True:
            try:
                return Pyro4.locateNS()
            except Pyro4.errors.PyroError:
                logger.info('Unable to locate name server. Waiting...')
                time.sleep(wait)

    #Catch keyboard interrupt
    except KeyboardInterrupt:
        logger.debug('Keyboard interupt while locating name server.\
                     Terminating!')
        sys.exit(0)


def start_config_server(host=None, port=6563, name='config_server',
                        wait=120, logger=None, *args, **kwargs):
    '''
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
    '''
    if logger is None:
        logger = DummyLogger()

    if host is None:
        host = get_own_ip()

    with Pyro4.Daemon(host=host, port=port) as daemon:

        #Locate the name server
        name_server = locate_name_server(wait=wait)
        logger.info('Found name server.')

        #Create a ConfigServer object
        config_server = ConfigServer(*args, **kwargs)

        #Register with pyro & the name server
        uri = daemon.register(config_server)
        name_server.register(name, uri)
        logger.info(f'ConfigServer object registered as: {uri}')

        #Request loop
        try:
            logger.info('Entering request loop... ')
            daemon.requestLoop()
        finally:
            logger.info('Unregistering from name server...')
            name_server.remove(name=name)


def query_config_server(key=None, name='config_server', logger=None, wait=None):
    '''
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
    '''
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
                raise(e)

        except Exception as e:
            logger.error(f'Unable to load remote config: {e}')
            raise(e)

#==============================================================================

def load_device_config(key=None, config_files=None, logger=None, wait=None,
                       **kwargs):
    '''
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
    '''
    if logger is None:
        logger = DummyLogger()

    if key is None:
        key = get_own_ip()

    #Load config from local files?
    if config_files is not None:
        logger.debug(f'Loading config from local file(s).')
        config = load_config(config_files, **kwargs)[key]

    #Load config from the config server?
    else:
        logger.debug(f'Loading remote config with key: {key}')
        config = query_config_server(key=key, logger=logger, wait=wait)

    return config

#==============================================================================

