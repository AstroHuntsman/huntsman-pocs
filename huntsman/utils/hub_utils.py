#A Python interface for the acroname USB Hubs - tested and functional

import brainstem
import time
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
        
        stem connection     
    
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


#Test main for bug fixes
          
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


    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    


