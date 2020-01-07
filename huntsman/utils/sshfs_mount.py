#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 07:16:00 2019

@author: danjampro

Run this on the pis (not the main computer).
"""
import os, subprocess
from huntsman.utils import load_config, DummyLogger
from huntsman.utils.config import load_device_config

#==============================================================================

def mount(mountpoint, remote, server_alive_interval=20,
          server_alive_count_max=3, logger=None):
    '''
    Mount remote on local.
    '''
    if logger is None:
        logger = DummyLogger()
        
    try:
        os.makedirs(mountpoint, exist_ok=True)
    except FileExistsError:
        pass #For some reason this is necessary
        
    options = f'ServerAliveInterval={server_alive_interval},' + \
              f'ServerAliveCountMax={server_alive_count_max}'
    options = ['sshfs', remote, mountpoint, '-o', options]
    try:
        subprocess.run(options, shell=False, check=True)
    except Exception as e:
        logger.error(f'Failed to mount {remote} on {mountpoint}: {e}')
        raise(e)
    
    
def unmount(mountpoint, logger=None):
    '''
    Unmount remote from local.
    '''
    if os.path.isdir(mountpoint):
        options = ['fusermount', '-u', mountpoint]
        try:
            subprocess.run(options, shell=False, check=True)
        except:
            if logger is None:
                logger = DummyLogger()
            logger.warning('Unable to unmount existing mountpoint.')
        
#==============================================================================
     
def get_user(default='huntsman', key='PANUSER', logger=None):
    '''
    Return the default user. 
    '''
    if key in os.environ:
        user = os.environ[key]
    else:
        user = default
        msg = f'{key} environment variable not found. Using f{default} as user.'
        if logger is None:
            logger = DummyLogger()
        logger.warning(msg)
    return user


def get_mountpoint():
    '''
    Return the default mountpoint. In the future, this can use a config file.
    '''
    home = os.path.expandvars('$HOME')
    mountpoint = os.path.join(home, 'Huntsmans-Pro')
    return mountpoint
    
#==============================================================================
    
def mount_sshfs(logger=None, user=None, mountpoint=None, config_files=None,
                **kwargs):
    '''
    
    '''
    #Get the logger
    if logger is None:
        logger = DummyLogger()
        
    #Get SSH username from environment?
    if user is None:
        user = get_user(logger=logger)
        
    #Specify the mount point as ~/Huntsmans-Pro 
    if mountpoint is None:
        mountpoint = get_mountpoint()
    
    #Retrieve the IP of the remote
    config_camera = load_device_config(config_files=config_files, **kwargs)
    remote_ip = config_camera['messaging']['huntsman_pro_ip']
    
    #Specify the remote directory
    config_huntsman = load_config()    
    remote_dir = config_huntsman['directories']['base']
    remote = f"{user}@{remote_ip}:{remote_dir}"
    
    #Check if the remote is already mounted, if so, unmount
    logger.debug(f'Attempting to unmount {mountpoint}...')
    unmount(mountpoint, logger=logger)
    
    #Mount
    logger.debug(f'Mounting {remote} on {mountpoint}...')
    mount(mountpoint, remote, logger=logger)
    
    #Symlink the directories
    original = os.path.join(mountpoint, 'images')
    link = config_huntsman['directories']['images']
    
    #If link already exists, make sure it is pointing to the right place
    if os.path.exists(link):
        try:
            assert(os.path.islink(link))
            assert(os.path.normpath(os.readlink(link))==os.path.normpath(
                    original))
            logger.debug('Skipping link creation as it already exists.')
        except:
            msg = f'Cannot create link. File already exists: {link}'
            logger.error(msg)
            raise FileExistsError(msg)
    else:
        logger.debug('Creating symlink to images directory...')
        os.symlink(original, link, target_is_directory=True)
    
    logger.debug('Done mounting SSHFS!')
    
    return mountpoint
    
#==============================================================================

