import qhue
from os import path
from qhue import Bridge, QhueException, create_new_username

#note, light 5 can be 'uncommented' once installed, or causes problems using currently 


#deal with error system - should errors be sent to pocs? how does pocs handle error messages?

def manual_login_phillips_hue(hue_ip="10.88.21.10", verbose = False):
    
    """
    A way to manually login to the hue bridge, requires the button on the bridge to be pushed.
    Only useful should auto login fail and present at the dome.
    
    Inputs:
        
        hue_ip - the ip address of the hue bridge. This is is set to the default input "10.88.21.10" 
    
    """
    
    username = qhue.create_new_username(hue_ip)
    
    if verbose:
    
       print("The username created is", username)
    
    b = qhue.Bridge(hue_ip,username)
    
    return(b)
    
def automatic_login_phillips_hue(hue_ip = "10.88.21.10", file_path = "hue_username.txt", verbose = False):
    
    """
    Automatic connection to the hue bridge using a stored username.
    
    Functions:
        
        Creates a text file with stored username upon first connection to the bridge, will
        prompt the user to press the hue bridge button to connect for the fist time and writes
        the file to the central directory. 
        
        Should a username already exist, the stored username is read and used to log into the
        bridge automatically.
        
        If a new username cannot be saved, and error message will be sent to the user. At this point
        manual login may be nessesary.
        
    Inputs: 
        
        hue_ip: the ip address of the hue bridge. Set by default to "10.88.21.10"
        
        file_path: the file name of the text file that will be saved containing the current username
        
    Outputs:
        
        b: bridge connection
        
    """
    
    if not path.exists(file_path):
        
        while True:
            try:
                username = create_new_username(hue_ip)
                break
            except QhueException as err:
                print("Cannot create new username: {}".format(err))
                  
        with open(file_path, "w") as cred_file:
            cred_file.write(username)
            
            if verbose:
               print("Your hue username",username,"was created")
                   
    else:
        
        with open(file_path, "r") as cred_file:
            username = cred_file.read()
            
            if verbose:
               print("Login with username", username, "successful")
            
    bridge = Bridge(hue_ip, username)
    
    return(bridge)
    
def find_hue_light_index(bridge):
    
    """
    Check the index of any hue light connected to the bridge 
    
    Input:
        
        b: bridge connection, i.e b = automatic_login_phillips_hue()
        
    Returns: 
        
        info: Returns the index of each hue device connected to the bridge
        
    """
    
    lights = bridge.lights()
    
    for num, info in lights.items():
    
        info = print("{:10} {}".format(info['name'], num))
            
    return(info)
    
def hue_observing_mode(bridge, led_index, desk_index, verbose = False):
    
    """
    Function: Low red light for observing. Desk lamp off
    
    Inputs:
        
        b: connection to the bridge, i.e b = automatic_login_phillips_hue()
        
        led_index: the unique index of the hue LED, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1
        
        desk_index: index of desk lamp. At present, = 4 
    
    """
        
    bridge.lights[led_index].state(on = True, bri=100, hue=50, sat = 250)
    bridge.lights[desk_index].state(on = False)
    #b.lights[field_index].state(on = False)
       
    if verbose:
       
       print("Observing Mode Selected")
       
def hue_observing_bright_mode(bridge, led_index, desk_index, verbose = False):
    
    """
    Function: bright red light for observing and viewing. Desk lamp on
    
    Inputs:
        
        b: connection to the bridge, i.e b = automatic_login_phillips_hue()
        
        led_index: the unique index of the hue LED, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1
        
        desk_index: index of desk lamp. At present, = 4 
    
    """
        
    bridge.lights[led_index].state(on = True, bri=250, hue=100, sat = 250)
    bridge.lights[desk_index].state(on = True, bri=250, hue = 30000, sat = 20)
    #b.lights[field_index].state(on = False)
       
    if verbose:
        
       print("Observing Bright Mode Selected")
       
def hue_bright_mode(bridge, led_index, desk_index, verbose = False):
    
    """
    Function: Bright mode for both LED and desk lamp for desk cam to monitor dome
    
    Inputs:
        
        b: connection to the bridge, i.e b = automatic_login_phillips_hue()
        
        led_index: the unique index of the hue LED, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1
        
        desk_index: index of desk lamp. At present, = 4 
    
    """
        
    bridge.lights[led_index].state(on = True, bri = 250, hue = 30000, sat = 10)
    bridge.lights[desk_index].state(on = True, bri = 250, hue = 30000, sat = 10)
    #b.lights[field_index].state(on = False)
    
    if verbose:
        
       print("Bright Mode Selected")
       
def hue_lights_off(bridge, led_index, desk_index, verbose = False):
    
    """
    Function: Turns all lights off in the dome
    
    Inputs:
        
        b: connection to the bridge, i.e b = automatic_login_phillips_hue()
        
        led_index: the unique index of the hue LED, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1
        
        desk_index: index of desk lamp. At present, = 4 
    
    """
        
    bridge.lights[led_index].state(on = False)
    bridge.lights[desk_index].state(on = False)
    #bridge.lights[field_index].state(on = False)
    
    if verbose:
        
       print("All Lights Off")
    
def hue_flat_field(bridge, led_index, desk_index, field_index, verbose = False):
    
    """
    Function: Flat field function for a 3rd lamp, turns off other lights
    
    Inputs:
        
        b: connection to the bridge, i.e b = automatic_login_phillips_hue()
        
        led_index: the unique index of the hue LED, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1
        
        desk_index: index of desk lamp. At present, = 4
        
        field_index: index of flat field lamp. To be added to the system.
                     will be allocated index 5
    
    """
    
    bridge.lights[led_index].state(on = False)
    bridge.lights[desk_index].state(on = False)
    bridge.lights[field_index].state(on = True, bri = 250, hue = 30000, sat = 10) 
       
    if verbose:   
       
       print("Flat Field Mode Selected")
       
       
       
       
       
       
      
       
        
    
        
        

    
    
    
    















   
