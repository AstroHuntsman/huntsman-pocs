#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan  2 12:04:11 2020

@author: danjampro

Code to provide a config server using pyro.
"""
import os
import Pyro4
from huntsman.utils import load_config, get_own_ip

#==============================================================================

@Pyro4.expose
class ConfigServer():
    """
    Class representing the config server.
    """

    def __init__(self, config_file=None, **kwargs):
        '''
        
        '''
        if config_file is None:
            config_file = os.path.join(os.environ['HUNTSMAN_POCS'],
                                       'conf_files', 'camera_info_local.yaml')
            
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

def start_config_server(host=None, port=6563, name='config_server',
                        *args, **kwargs):
    '''
    
    '''
    if host is None:
        host = get_own_ip()
        
    with Pyro4.Daemon(host=host, port=port) as daemon:
        
        #Locate the name server
        name_server = Pyro4.locateNS()
        
        #Create a ConfigServer object
        config_server = ConfigServer(*args, **kwargs)
            
        #Register with pyro & the name server
        uri = daemon.register(config_server)
        name_server.register(name, uri)
        
        #Request loop
        try:
            daemon.requestLoop()
        finally:
            name_server.remove(name=name)
        
def query_config_server(key=None, name='config_server'):
    '''
    
    '''
    camera_server = Pyro4.Proxy(f'PYRONAME:{name}')
    return camera_server.get_config(key=key)
            
#==============================================================================

