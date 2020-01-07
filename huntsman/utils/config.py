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

#==============================================================================

@Pyro4.expose
class ConfigServer():
    '''
    Class representing the config server.
    '''
    def __init__(self, config_file=None, **kwargs):
        '''
        
        '''
        if config_file is None:
            config_file = os.path.join(os.environ['HUNTSMAN_POCS'],
                                       'conf_files', 'device_info.yaml')
            
        #Read the config file
        self.config = load_config(config_files=[config_file], **kwargs)
        
        
    def get_config(self, key=None):
        '''
        Retrieve the config file.
        '''
        if key is None:
            return self.config
        return self.config[key]
    
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
    if wait is None:
        return Pyro4.locateNS()
    
    try:
        #Look for NS periodically until it is found
        while True:
            try:
                return Pyro4.locateNS()
            except Pyro4.errors.PyroError:
                msg = 'Unable to locate name server. Waiting...'
                if logger is None:
                    print(msg)
                else:
                    logger.debug(msg)
                time.sleep(wait)
    
    #Catch keyboard interrupt
    except KeyboardInterrupt:
        msg = 'Keyboard interupt while locating name server. Terminating!'
        if logger is None:
            print(msg)
        else:
            logger.debug(msg)        
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
        
        
def query_config_server(key=None, name='config_server'):
    '''
    Query the config server.
    
    Parameters
    ----------
    key (str):
        The key used to query the config file. If none, the whole config is 
        returned.
    name (str):
        The name used to locate the config server from the Pyro name server.
    
    Returns
    -------
    dict:
        The config dictionary.
    '''
    config_server = Pyro4.Proxy(f'PYRONAME:{name}')
    return config_server.get_config(key=key)
            
#==============================================================================

def load_device_config(key=None, config_files=None, logger=None, **kwargs):
    '''
    Load the device config from either the config server or local files.
    
    Parameters
    ----------
    key:
        The key used to query the config server. Only used if config_files
        is None.
    config_files:
        List of config file names. If None (default), use the config server.
        
    Returns
    -------
    dict:
        The config dictionary.
    '''
    if logger is None:
        logger = DummyLogger()
        
    #Load config from local files?
    if config_files is not None:
        logger.debug(f'Loading config from local file(s).')
        try:
            config = load_config(config_files, **kwargs)
        except Exception as e:
            logger.error(f'Unable to load local config file(s): {e}')
            raise(e)
    
    #Load config from the config server?
    else:
        if key is None:
            key = get_own_ip()
        logger.debug(f'Loading remote config with key: {key}')
        try:
            config = query_config_server(key=key)
        except Exception as e:
            logger.error(f'Unable to load remote config: {e}')
            raise(e)
            
    return config
    
#==============================================================================

