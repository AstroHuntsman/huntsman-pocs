from warnings import warn

import Pyro4
from Pyro4 import naming, errors

from huntsman.utils import get_own_ip, load_config, sshfs_mount
from huntsman.utils.config import query_config_server
from huntsman.camera.pyro import CameraServer

#==============================================================================

def run_name_server(host=None, port=None, autoclean=0):
    """
    Runs a Pyro name server.

    The name server must be running in order to use distributed cameras with POCS. The name server
    should be started before starting camera servers or POCS.

    Args:
        host (str, optional): hostname/IP address to bind the name server to. If not given then
            get_own_ip will be used to attempt to automatically determine the IP addresses of
            the computer that the name server is being started on.
        port (int, optional): port number to bind the name server to. If not given then the port
            will be selected automatically (usually 9090).
        autoclean (int, optional): interval, in seconds, for automatic deregistration of objects
            from the name server if they cannot be connected. If not given no autocleaning will
            be done.
    """
    try:
        # Check that there isn't a name server already running
        name_server = Pyro4.locateNS()
    except errors.NamingError:
        if not host:
            # Not given an hostname or IP address. Will attempt to work it out.
            host = get_own_ip(verbose=True)
        else:
            host = str(host)

        if port is not None:
            port = int(port)

        Pyro4.config.NS_AUTOCLEAN = float(autoclean)

        print("Starting Pyro name server... (Control-C/Command-C to exit)")
        naming.startNSloop(host=host, port=port)
    else:
        print("Pyro name server {} already running! Exiting...".format(name_server))


def run_camera_server(ignore_local, unmount_sshfs=True, use_server=False):
    """
    Runs a Pyro camera server.

    The camera server should be run on the camera control computers of distributed cameras. The
    camera servers should be started after the name server, but before POCS.

    Args:
        ignore_local (bool, optional): If True use the default
        $HUNTSMAN_POCS/conf_files/pyro_camera.yaml only. If False will allow
        $HUNTSMAN_POCS/conf_files/pyro_camera_local.yaml to override the default configuration.
        Default False.
        
        unmount_sshfs (bool, optional): If True, unmounts the sshfs upon 
            termination of the camera server.
            
        use_server (bool, optional): If True, queries the config server for the
            config file using the local IP address. This will override any other 
            config file.
    """
    #Mount the SSHFS
    mountpoint = sshfs_mount.mount_sshfs()
    
    Pyro4.config.SERVERTYPE = "multiplex"
        
    #Load the config file 
    if use_server:
        ip_address = get_own_ip()
        config = query_config_server(key=ip_address)
    else:
        config = load_config(config_files=['pyro_camera.yaml'],
                             ignore_local=ignore_local)
    
    host = config.get('host', None)
    if not host:
        host = get_own_ip(verbose=True)
    port = config.get('port', 0)

    with Pyro4.Daemon(host=host, port=port) as daemon:
        try:
            name_server = Pyro4.locateNS()
        except errors.NamingError as err:
            warn('Failed to locate Pyro name server: {}'.format(err))
            exit(1)
        print('Found Pyro name server')
        uri = daemon.register(CameraServer)
        print('Camera server registered with daemon as {}'.format(uri))
        name_server.register(config['name'], uri, metadata={"POCS",
                                                            "Camera",
                                                            config['camera']['model']})
        print('Registered with name server as {}'.format(config['name']))
        print('Starting request loop... (Control-C/Command-C to exit)')
        try:
            daemon.requestLoop()
        finally:
            print('\nShutting down...')
            name_server.remove(name=config['name'])
            print('Unregistered from name server')

            #Unmount the SSHFS?
            if unmount_sshfs:
                sshfs_mount.unmount(mountpoint)
                    
#==============================================================================
       
        

        