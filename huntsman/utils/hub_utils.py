# A Python interface for the acroname USB Hubs - tested and functional

# Please note that the Yaml config file that monique is working on is not yet finalised and is not accessable in POCS yet
# so not sure what the best approach is here to retrieve info from the
# file - this can be updated once this is finished

import brainstem
import yaml
from brainstem.result import Result
from time import sleep
from enum import IntEnum


class Lights(IntEnum):
    OFF = 0
    ON = 1

def connect_to_hub(hub_serial, verbose=False, toggle_leds=True):
    """Used to connect to the hub and create stem.

    Args:

        hub_serial (int): Serial number of the hub in use.

        toggle_leds (bool): If true, will flash user LED's to verify that a connection has
        been made.

    Returns:

        stem (str): Connection to hub

    """
    if verbose:
        print('Connecting to hub', hub_serial)
    stem = brainstem.stem.USBHub3p()
    result = stem.discoverAndConnect(brainstem.link.Spec.USB, hub_serial)
    if result == (Result.NO_ERROR):
        result1 = stem.system.getSerialNumber()
        if verbose:
            print('Connected to USBStem with serial number:', result1)
        stem.system.setLED(Lights.ON)
        if toggle_leds:
            if verbose:
                print('Flashing the user LED on device')
            for i in range(0, 101):
                flash = stem.system.setLED(i % 2)
            if flash != brainstem.result.Result.NO_ERROR:                
                sleep(0.1)
    else:
        if verbose:
            print('Could not find hub with serial number:', hub_serial)

    return(stem)


def yaml_import(
        no_camera=0,
        yaml_file="/Users/SC09015/Desktop/Astro/Code/device_info_testing_file.yaml"):
    """Used to reterive serial number of hub and port number on the hub for selected camera

    Args:

        no_camera (int): The camera number in the yaml file between 0 - number of cameras -1

        yaml_file (str): Location of the yaml file

    Returns:

        hub_serial (int): The serial number of the hub in use by the selected camera

        port (int): The hub usb port the camera is connected to

    """

    with open(yaml_file, 'r') as yml:
        try:
            newyml = (yaml.load(yml))
            hub_serial = newyml['cameras'][1]['devices'][no_camera]['USB_hub_serial_number']
            port = newyml['cameras'][1]['devices'][no_camera]['camera_into_serial_adaptor_port']
        except yaml.YAMLError as exc:
            print(exc)
    return(hub_serial, port)

def disconnect_from_hub(stem, hub_serial, verbose=False):
    """Disconnects from the hub

    Args:

        stem (str): Stem connection to usb hub, returned from 'connect to hub' function

        hub_serial (int): The serial number of the hub in use

        port (int): The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname

    """
    stem.disconnect()
    print('Disconnected from hub', hub_serial)

def get_port_voltage(stem, port):
    """Returns a voltage reading for a specified port on the hub

    Args:

        stem (str): Stem connection to usb hub, returned from 'connect to hub' function

        hub_serial (int): The serial number of the hub in use

        port (int): The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname

    Returns:

        voltage (int): The voltage across the chosen usb port

    """

    voltage = stem.usb.getPortVoltage(port)
    return(voltage)

def get_port_current(stem, port):
    """Returns a current reading for a specified port on the hub

    Args:

        stem (str): Stem connection to usb hub, returned from 'connect to hub' function

        hub_serial (int): The serial number of the hub in use

        port (int): The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname

    Returns:

        current (int): The current supplied to the chosen usb port

    """
    current = stem.usb.getPortCurrent(port)
    return(current)
    
def port_enable(stem, port, toggle_leds=False):
    """Enables a specified port

    Args:

        stem (str): Stem connection to usb hub, returned from 'connect to hub' function

        hub_serial (int): The serial number of the hub in use

        port (int): The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname
    """
    stem.usb.setPortEnable(port)
    if toggle_leds:
        for i in range(1, 11):
            stem.system.setLED(i % 2)

def port_disable(stem, port, toggle_leds=False):
    """Disables a specified port

    Args:

        stem (str): Stem connection to usb hub, returned from 'connect to hub' function

        hub_serial (int): The serial number of the hub in use

        port (int): The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname
    """

    stem.usb.setPortDisable(port)
    if toggle_leds:
        for i in range(1, 11):
            stem.system.setLED(i % 2)