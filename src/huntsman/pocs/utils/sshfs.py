import os
import subprocess
from huntsman.pocs.utils import DummyLogger
from huntsman.pocs.utils.config import query_config_server, load_device_config


def mount(mountpoint, remote, server_alive_interval=20, logger=None,
          server_alive_count_max=3, strict_host_key_checking=False):
    """
    Mount remote on local.

    Arguments
    ---------
    strict_host_key_checking:
        Should be False to avoid user interaction when running in a docker
        container.
    """
    if logger is None:
        logger = DummyLogger()
    logger.debug(f'Mounting {remote} on {mountpoint}...')

    try:
        os.makedirs(mountpoint, exist_ok=True)
    except FileExistsError:
        pass  # For some reason this is necessary

    # SSH options
    strict_host_key_checking = "yes" if strict_host_key_checking else "no"
    options = f'ServerAliveInterval={server_alive_interval},' + \
              f'ServerAliveCountMax={server_alive_count_max},' + \
              f'StrictHostKeyChecking={strict_host_key_checking}'
    options = ['sshfs', remote, mountpoint, '-o', options]

    try:
        subprocess.run(options, shell=False, check=True)

        logger.info(f'Successfully mounted {remote} at {mountpoint}!')

    except Exception as e:
        logger.error(f'Failed to mount {remote} at {mountpoint}: {e}')
        raise (e)


def unmount(mountpoint, logger=None):
    """
    Unmount remote from local.
    """
    if os.path.isdir(mountpoint):
        options = ['fusermount', '-u', mountpoint]
        try:
            subprocess.run(options, shell=False, check=True)
        except Exception:
            if logger is None:
                logger = DummyLogger()
            logger.warning(f'Unable to unmount {mountpoint}.')


def get_user(default='huntsman', key='PANUSER', logger=None):
    """
    Return the user.
    """
    if key in os.environ:
        user = os.environ[key]
    else:
        user = default
        msg = f'{key} environment variable not found. Using f{default} as user.'
        if logger is None:
            logger = DummyLogger()
        logger.warning(msg)
    return user


def mount_images_dir(logger=None, user=None, mountpoint=None, config=None,
                     **kwargs):
    """
    Mount the images directory from the NGAS server to the local device.
    """
    # Setup the logger
    if logger is None:
        logger = DummyLogger()

    # Load the config
    if config is None:
        config = load_device_config(logger=logger, **kwargs)

    # Specify user for SSHFS connection
    if user is None:
        user = get_user(logger=logger)

    # Specify the mount point on the local device
    if mountpoint is None:
        mountpoint = config['directories']['images']

    # Retrieve the IP of the remote
    remote_ip = query_config_server(key='control', logger=logger,
                                    )['ip_address']

    # Specify the remote directory
    remote_dir = query_config_server(key='control',
                                     logger=logger)['directories']['images']
    remote = f"{user}@{remote_ip}:{remote_dir}"

    # Mount
    mount(mountpoint, remote, logger=logger)

    return mountpoint
