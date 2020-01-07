#!/usr/bin/env python
"""
Script to mount the SSHFS. This is done automatically when starting a pyro
camera server, but this script is also included for potential convenience.
"""
import argparse
from huntsman.utils import sshfs_mount

#==============================================================================

if __name__ == "__main__":
        
    #Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument('--unmount', help='Unmount the SSHFS',
                        action='store_true')
    args = parser.parse_args()
    
    #Unmount the SSHFS?
    if args.unmount:
        mountpoint = sshfs_mount.get_mountpoint()
        sshfs_mount.unmount(mountpoint)
    
    else:   
        #Mount the SSHFS
        sshfs_mount.mount_sshfs()