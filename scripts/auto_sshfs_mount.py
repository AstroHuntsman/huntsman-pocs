#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 07:16:00 2019

@author: danjampro

Run this on the pis (not the main computer).
"""
import os, subprocess
from huntsman.utils import load_config

#==============================================================================

def mount(local, remote, server_alive_interval=20, server_alive_count_max=3,
          logger=None):
    '''
    Mount remote on local.
    '''
    if logger is None:
        logger = print
        
    if not os.path.isdir(local):
        try:
            os.makedirs(local, exist_ok=True)
        except FileExistsError:
            pass #For some reason this is necessary
        
    options = f'ServerAliveInterval={server_alive_interval},' + \
              f'ServerAliveCountMax={server_alive_count_max}'
    options = ['sshfs', remote, local, '-o', options]
    try:
        subprocess.run(options, shell=False, check=True)
    except Exception as e:
        logger(f'Failed to mount {remote} on {local}.')
        raise(e)
    
    
def attempt_unmount(local):
    '''
    Unmount remote from local.
    '''
    if os.path.isdir(local):
        options = ['fusermount', '-u', local]
        try:
            subprocess.run(options, shell=False, check=True)
        except:
            pass
        
#==============================================================================

def mount_sshfs(logger=None):
    '''
    
    '''
    if logger is None:
        logger = print
        
    #Specify the mount point as ~/Huntsmans-Pro (for huntsman user)
    home = os.path.expandvars('$HOME')
    local = os.path.join(home, 'Huntsmans-Pro')
    
    #Specify the remote directory
    config = load_config()
    remote_ip = config['messaging']['huntsman_pro_ip']
    remote_dir= config['directories']['base']
    remote = f"huntsman@{remote_ip}:{remote_dir}"
    
    #Check if the remote is already mounted, if so, unmount
    logger(f'Attempting to unmount {local}...')
    attempt_unmount(local)
    
    #Mount
    logger(f'Mounting {remote} on {local}...')
    mount(local, remote)
    
    #Symlink the directories
    original = os.path.join(local, 'images')
    link = config['directories']['images']
    
    #If link already exists, make sure it is pointing to the right place
    if os.path.exists(link):
        try:
            assert(os.path.islink(link))
            assert(os.path.normpath(os.readlink(link))==os.path.normpath(
                    original))
            logger('Skipping link creation as it already exists.')
        except:
            msg = f'Cannot create link. File already exists: {link}'
            logger(msg)
            raise FileExistsError(msg)
    else:
        logger('Creating symlink to images directory...')
        os.symlink(original, link, target_is_directory=True)
    
    logger('Done mounting SSHFS!')
        
#==============================================================================
#==============================================================================

if __name__ == '__main__':
    
    mount_sshfs()