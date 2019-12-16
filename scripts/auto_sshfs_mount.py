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

def Mount(local, remote, ServerAliveInterval=20, ServerAliveCountMax=3):
    '''
    Mount remote on local.
    '''
    if not os.path.isdir(local):
        os.mkdirs(local)
        
    options = f'ServerAliveInterval={ServerAliveInterval},' + \
              f'ServerAliveCountMax={ServerAliveCountMax}'
    options = ['sshfs', remote, local, '-o', options]
    try:
        subprocess.run(options, shell=False, check=True)
    except Exception as e:
        print(f'Failed to mount {remote} on {local}.')
        raise(e)
    
    
def AttemptUnmount(local):
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
#==============================================================================

if __name__ == '__main__':
    
    #Specify the mount point as ~/Huntsmans-Pro (for huntsman user)
    home = os.path.expandvars('$HOME')
    local = os.path.join(home, 'huntsman', 'Huntsmans-Pro')
    
    #Specify the remote directory
    config = load_config()
    remote_ip = config['messaging']['huntsman_pro_ip']
    remote_dir= config['directories']['base']
    remote = f"huntsman@{remote_ip}:{remote_dir}"
    
    #Check if the remote is already mounted, if so, unmount
    print(f'Attempting to unmount {local}...')
    AttemptUnmount(local)
    
    #Mount
    print(f'Mounting {remote} on {local}...')
    Mount(local, remote)
    
    #Symlink the directories
    original = os.path.join(local, 'images')
    link = config['directories']['images']
    
    #If link already exists, make sure it is pointing to the right place
    if os.path.exists(link):
        try:
            assert(os.path.islink(link))
            assert(os.path.normpath(os.readlink(link))==os.path.normpath(
                    original))
            print('Skipping link creation as it already exists.')
        except:
            raise FileExistsError(
                    f'Cannot create link. File already exists: {link}')
    else:
        print('Creating symlink to images directory...')
        os.symlink(original, link, target_is_directory=True)
    
    print('Done!')
    
    
    
