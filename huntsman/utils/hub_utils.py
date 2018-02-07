import brainstem
import yaml
from brainstem.result import Result
from enum import IntEnum

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

    def __init__(self):
        no_camera = 0
        yaml_file = "/Users/SC09015/Desktop/Python_Control_Central/device_info_testing_file2.yaml"
        self.verbose = True
        self.toggle_leds = True
        self.hub_serial = 0xcd12637d
        #with open(yaml_file, 'r') as yml:
          #  try:
           #     newyml = (yaml.load(yml))
           #     self.hub_serial = newyml['cameras'][1]['devices'][no_camera]['USB_hub_serial_number']
           #     self.port = newyml['cameras'][1]['devices'][no_camera]['camera_into_serial_adaptor_port']
          #  except yaml.YAMLError as exc:
          #      print(exc)

        if self.verbose:
            print('Connecting to hub', self.hub_serial)
            
        self.stem = brainstem.stem.USBHub3p()
        
        result = self.stem.discoverAndConnect(brainstem.link.Spec.USB, self.hub_serial)
        
        if result == (Result.NO_ERROR):
            result1 = self.stem.system.getSerialNumber()
            
        else:
            print('Could not connect to the device')
            
        if self.verbose:
            print('Connected to USBStem with serial number:', result1)
            
        self.stem.system.setLED(Lights.ON)
        
        if self.toggle_leds:
            if self.verbose:
                print('Flashing the user LED on device')
            for i in range(0, 101):
                self.stem.system.setLED(i % 2)
            

    def disconnect_from_hub(self):
        """Used to disconect from the USB hub"""
        self.stem.disconnect()
        print('Disconnected from hub', self.hub_serial)

    def voltage(self, port):
        """Prints the voltage across the chosen port in volts"""
        voltage = self.stem.usb.getPortVoltage(port).value
        voltage_out = voltage * 1e-6 
        print(voltage_out)

    def current(self, port):
        """Prints the current through the chosen port in amps"""
        current = self.stem.usb.getPortCurrent(port).value
        current_out = current * 1e-6
        print(current_out)

    def enable(self, port):
        """Enables a specific port"""
        self.stem.usb.setPortEnable(port)
        if self.toggle_leds:
            for i in range(1, 11):
                self.stem.system.setLED(i % 2)

    def disable(self, port):
        """Dissables a specific port"""
        self.stem.usb.setPortDisable(port)
        if self.toggle_leds:
            for i in range(1, 11):
                self.stem.system.setLED(i % 2)
                
    def disable_all(self):
        
        ports = [0,1,2,3,4,5,6,7]
        for port_id in ports:
            self.stem.usb.setPortDisable(port_id)
            
    def enable_all(self):
        
        ports = [0,1,2,3,4,5,6,7]
        for port_id in ports:
            self.stem.usb.setPortEnable(port_id)        

            