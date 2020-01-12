#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The aim of this code is for the device to look up its own task and start the 
necessary processes automatically.

This code is ideally run from inside the latest huntsman docker container.
"""
from huntsman.utils.config import load_device_config

#==============================================================================

def get_device_type():
    '''
    Retrieve the type of this device.
    '''
    #Retrieve the device config from the config server, using own IP
    config = load_device_config()

    return config['type']
    
#==============================================================================
#==============================================================================

if __name__ == '__main__':
    
    #Retrieve the device type
    device_type = get_device_type()
    
    #Camera server...
    #==========================================================================    
    if device_type == 'camera':
        
        #Only attempt imports here to be as lightweight as possible
        from huntsman.utils.pyro import run_camera_server
        run_camera_server()
        
    #Dome server...
    #==========================================================================
    #elif device_type == 'dome':
        
    #Unrecongnised device type...
    #==========================================================================
    else:
        raise NotImplementedError(
                f'Device type not implemented: {device_type}')
    
    
    