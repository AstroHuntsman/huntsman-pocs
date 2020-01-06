#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan  2 12:04:11 2020

@author: danjampro

Code to provide a config server using pyro.
"""
import os, time
import Pyro4
from huntsman.utils import load_config, get_own_ip

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
        
        
def start_config_server(host=None, port=6563, name='config_server',
                        wait=120, *args, **kwargs):
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
        
        print(f'ConfigServer object registered as: {uri}')
        
        #Request loop
        try:
            print('Entering request loop... ')
            daemon.requestLoop()
        finally:
            print('Unregistering from name server...')
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

