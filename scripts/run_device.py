"""
The aim of this code is for the device to look up its own task and start the
necessary processes automatically.

This code is ideally run from inside the latest huntsman docker container.
"""
from huntsman.pocs.utils.config import load_device_config


def get_device_type(**kwargs):
    '''
    Retrieve the type of this device.
    '''
    # Retrieve the device config from the config server, using own IP
    config = load_device_config(**kwargs)

    return config['type']


if __name__ == '__main__':

    # Retrieve the device type
    device_type = get_device_type(wait=60)

    # Camera server...
    if device_type == 'camera':

        # Only attempt imports here to be as lightweight as possible
        from huntsman.pocs.utils.pyro.camera_server import run_camera_server
        run_camera_server()

    # Dome server...
    # elif device_type == 'dome':

    # Unrecongnised device type...
    else:
        raise NotImplementedError(
            f'Device type not implemented: {device_type}')
