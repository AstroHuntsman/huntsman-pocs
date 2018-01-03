#A Python interface for the acroname USB Hubs - tested and functional

#Please note that the Yaml config file that monique is working on is not yet finalised and is not accessable in POCS yet
# so not sure what the best approach is here to retrieve info from the file - this can be updated once this is finished 

import brainstem
import time
import yaml
from brainstem.result import Result
from time import sleep


def connect_to_hub(hub_serial, verbose = False, test = True):
    
    """
    Function: Used to connect to the hub and create stem
    
    Inputs:
        
        hub_serial: Serial number of the hub
        
        test: If true, will flash user LED's to verify that a connection has 
        been made 
        
    Outputs: 
        
        stem: Connection to hub    
    
    """
    
    print('Connecting to hub', hub_serial)
    
    stem = brainstem.stem.USBHub3p() 

    result = stem.discoverAndConnect(brainstem.link.Spec.USB, hub_serial)

    if  result == (Result.NO_ERROR):
        
        result1 = stem.system.getSerialNumber()
        
        print ('Connected to USBStem with serial number:', result1)
    
        stem.system.setLED(1)
        
        if test == True:
            
            if verbose: True
            
            print('Flashing the user LED on device')
    
            for i in range(0,101):
        
               flash = stem.system.setLED(i % 2)
        
            if flash != brainstem.result.Result.NO_ERROR:
            

              sleep(0.1)  
    else:
        
         print('Could not find hub with serial number:', hub_serial)
         
        
    return(stem)
    
def yaml_import(no_camera = 0, yaml_file = "/Users/SC09015/Desktop/Astro/Code/device_info_testing_file.yaml"):

    """
    Function: Used to reterive serial number of hub and port number on the hub for selected camera
    
    Inputs:
        
        no_camera: The camera number in the yaml file between 0 - number of cameras -1
        
        yaml_file: Location of the yaml file
    
    Outputs:
        
        hub_serial: The serial number of the hub in use by the selected camera
        
        port: The hub usb port the camera is connected to
        
    """
    
    
    with open(yaml_file, 'r') as yml: # as stream:
        
        try:
            newyml = (yaml.load(yml))
            
            hub_serial = newyml['cameras'][1]['devices'][no_camera]['USB_hub_serial_number']
            
            port = newyml['cameras'][1]['devices'][no_camera]['camera_into_serial_adaptor_port']
            
        except yaml.YAMLError as exc:
            print(exc)                      #standard yaml error
            
    return(hub_serial, port)

"""
Function: The following functions perform basic tasks to control the USB hub and ports as well as retrive performance infomation 

Inputs:
    
    stem: Stem connection to usb hub, returned from 'connect to hub' function
    
    hub_serial: The serial number of the hub in use
    
    port: The USB port number on the chosen hub, an integer between 0 - 7 for this model acroname
    
Outputs:
    
    voltage: The voltage across chosen usb port
    
    current: The current being drawn from the chosen usb port

"""        
            
    
def disconnect_from_hub(stem, hub_serial, verbose = False):

    stem.disconnect() 
    
    print('Disconnected from hub', hub_serial)
    
    return()
    

def get_port_voltage(stem, port):
    
    voltage = stem.usb.getPortVoltage(port)
    
    return(voltage)
    

def get_port_current(stem, port):
    
    current = stem.usb.getPortCurrent(port)
     
    return(current)
    
#remember stem = stem_serial if this doesnt work
         
def port_enable(stem, port, test = False):
    
    stem.usb.setPortEnable(port)
    
    if test == True:
        
       for i in range(1, 11):
    
          stem.system.setLED(i % 2)
          time.sleep(2)
 

def port_disable(stem, port, test = False):
    
    stem.usb.setPortDisable(port)
    
    if test == True:
        
       for i in range(1, 11):
    
          stem.system.setLED(i % 2)
          time.sleep(2)


#Test main for bug fixes - tested on site, all working
          
def main():
    
    hub_serial = 0xCD12637D
    port = 0
    
    stem = connect_to_hub(hub_serial)
     
    #Connect to hub1 port 0, turn on and get current and voltage reading turn off
    #and disconnect
    
    port_enable(stem, port, test = True)
    
    current = get_port_current(stem, port)
    print("The current output through port", port, "is", current.value)
    
    voltage = get_port_voltage(stem, port)
    print("The voltage output from port", port, "is", voltage.value)
    
    port_disable(stem, port)
    
    disconnect_from_hub(stem, hub_serial)
    
    return()


    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    


