import brainstem
import time
from enum import IntEnum
from pocs.utils.config import load_config
from nested_lookup import nested_lookup
from warnings import warn

class Lights(IntEnum):
    """Lights class inherited from IntEnum to set OFF to 0 and ON to 1 """
    OFF = 0
    ON = 1

class Hub_Interface(object):
    """The python interface for an Acroname USB Hub

      Attributes:
          no_camera(int): The camera number specified in the config yaml file
          yaml_file(str): The full path to the yaml config file being used
          verbose(bool): Can be True of Flase to give more infomation about the method performed
          toggle_leds(bool): Set to True, this will flash the User LEDs when a command is performed
          stem(str): The connection to the usb hub
          hub_serial(int): The serial number of the USB hub
          port(int): The port number of the USB hub that is in use
    """

    def __init__(self, state):

        usb_config_path = "/private/var/huntsman/huntsman-pocs/conf_files/test_huntsman_config.yaml"
        self.config = load_config(usb_config_path)
        self.verbose = True
        self.possible_states = ('observing', 'shut_down', 'start_her_up', 'power_cycle', 'pass')
        if state not in self.possible_states:
            raise ValueError("State chosen is not recognised")
        self.toggle_leds = True
        self.full_set = [0,1,2,3,4,5,6,7]
        hubs = nested_lookup("USB_hub_serial_number", self.config) 
        camera_ports = nested_lookup("camera_into_USBhub_port", self.config)       
        birger_ports = nested_lookup("serial_adaptor_into_USBhub_port", self.config)
        paired_states = list(zip(hubs, camera_ports, birger_ports))
        yaml_devices = list(range(0, len(paired_states)))
        for n in yaml_devices:
            if state == "pass":
                pass
        else:
                ensamble = paired_states[n]
                hub_serial = ensamble[0]
                camera_port = ensamble[1]
                birger_port = ensamble[2]
                if hub_serial == 'OXCD12637D':
                    hub_serial = 0xcd12637d
                if hub_serial == 'OX518EFFE1':
                    hub_serial = 0x518effe1
                "Connect to the Hub"
                if self.verbose:
                    print('Connecting to hub', hub_serial)                    
                print("step1")
                self.stem = brainstem.stem.USBHub3p()
                result = self.stem.discoverAndConnect(brainstem.link.Spec.USB, hub_serial)
                if result == (result.Result.NO_ERROR):
                    result1 = self.stem.system.getSerialNumber()
                    if self.verbose:
                        print('Connected to USBStem with serial number:', result1)
                else:
                    warn('Could not connect to the device')
                self.stem.system.setLED(Lights.OFF)
                if self.toggle_leds:
                    if self.verbose:
                        print('Flashing the user LED on device')
                    for i in range(0, 101):
                        self.stem.system.setLED(i % 2)
                #enable all ports needed for observing and all hubs in use
                if state == "observing":
                    self.stem.usb.setPortEnable(camera_port)
                    self.stem.usb.setPortEnable(birger_port)
                #shut down all ports in use on all hubs in use and disconnect
                if state == "shut_down":
                    self.stem.usb.setPortDisable(camera_port)
                    self.stem.usb.setPortDisable(birger_port)
                    self.stem.disconnect()
                #start up all ports from hubs in use
                if state == "start_her_up":
                    for chosen_hub in hubs:
                        self.stem.discoverAndConnect(brainstem.link.Spec.USB, 
                                                     chosen_hub)
                        for port_id in self.full_set:
                            self.stem.usb.setPortEnable(port_id)
                #power cycle every hub in use
                if state == "power_cycle":
                     for chosen_hub in hubs:
                         self.stem.discoverAndConnect(brainstem.link.Spec.USB, 
                                                      chosen_hub)
                         for port_id in self.full_set:
                            self.stem.usb.setPortDisable(port_id)
                            time.sleep(30)
                            self.stem.usb.setPortEnable(camera_port)
                            self.stem.usb.setPortEnable(birger_port)