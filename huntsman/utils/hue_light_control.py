import yaml
from os import path
from qhue import Bridge, QhueException, create_new_username

class Hue_Lights(object):
     """A Python interface for the lighting control system of the huntsman dome
            
     Attributes:
         hue_ip(int): the ip address of the hue bridge. 
         led_index(int): the index of the led light strip found in the config file
         desk_index(int): the index of the desk lamp found in config file
         flat_index(int): the index of the flat field light that will eventually be addd to the config file
         username_file_path(str): the file path of the text file that will be saved containing the current username 
         verbose(bool): can be set to True or False to provide extra info if needed
         
    """
    def __init__(self):

        yamlf = "/Users/SC09015/Desktop/Astro/Code/huntsman-pocs/conf_files/set_lights.yaml"
        with open(yamlf, 'r') as yml:
            try:
                newyml = (yaml.load(yml))
                self.hue_ip = newyml['hue_lights'][0]['hue_ip']
                self.username_file_path = newyml['hue_lights'][1]['file_path']
                self.led_index = newyml['hue_lights'][2]['index']['led_index']
                self.desk_index = newyml['hue_lights'][2]['index']['desk_index']
                self.flat_index = newyml['hue_lights'][2]['index']['flat_index']
                self.verbose = False
            except yaml.YAMLError as error:
                print(error)

    def login(self):
        """Automatic login to the hue bridge using a stored username.
        Creates a text file with stored username upon first connection to the bridge, will
        prompt the user to press the hue bridge button to connect for the fist time and writes
        the file to the working directory.
        Should a username already exist, the stored username is read and used to log into the
        bridge automatically.
        If a new username cannot be saved, and error message will be sent to the user. At this point
        manual login may be nessesary.
        
        Attributes:
            username_file_path(str): the file path of the text file that will be saved containing the current username
            bridge(str): bridge connection
            verbose(bool): can be set to True or False to provide extra info if needed
            hue_ip(int): the ip address of the hue bridge. 
        """

        if not path.exists(self.username_file_path):
            try:
                username = create_new_username(self.hue_ip)
            except QhueException as err:
                print("Cannot create new username: {}".format(err))
            with open(self.username_file_path, "w") as cred_file:
                cred_file.write(username)
                if self.verbose:
                    print("Your hue username", username, "was created")
        else:
            with open(self.username_file_path, "r") as cred_file:
                username = cred_file.read()
                if self.verbose:
                    print("Login with username", username, "successful")

        self.bridge = Bridge(self.hue_ip, username)

    def get_username(self):
        """Used to return the username saved in a text file 
        
        Attributes:
            file_path(str): the file name of the text file that will be saved containing the current username
        """
        
        with open(self.username_file_path, 'r') as user:
            if not path.exists(self.username_file_path):
                print("Username cannot be found")
            else:
                username = user.read()
        print(username)

    def get_index(self):
        """Used to return the index of each of the devices connected to the bridge should a factory reset occur"""
        lights = self.bridge.lights()
        for num, info in lights.items():
            info = print("{:10} {}".format(info['name'], num))
        print(info)

    def observing_mode(self):
        """The observing mode for the huntsman system
        
        Attributes:
            bridge(str): bridge connection
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_index(int): the index of the led light strip found in the config file   
        """
        self.bridge.lights[self.led_index].state(
            on=True, bri=100, hue=50, sat=250)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Observing Mode Selected")

    def observing_bright_mode(self):
        """A bright observing mode for the huntsman system
        
        Attributes:
            bridge(str): bridge connection
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_index(int): the index of the led light strip found in the config file 
        """
        self.bridge.lights[self.led_index].state(
            on=True, bri=250, hue=100, sat=250)
        self.bridge.lights[self.desk_index].state(
            on=True, bri=250, hue=30000, sat=20)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Observing Bright Mode Selected")

    def bright_mode(self):
        """The bright mode for the huntsman, used to observe the system through the webcame
        
        Attributes:
            bridge(str): bridge connection
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_index(int): the index of the led light strip found in the config file 
        """
        self.bridge.lights[self.led_index].state(
            on=True, bri=250, hue=30000, sat=10)
        self.bridge.lights[self.desk_index].state(
            on=True, bri=250, hue=30000, sat=10)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Bright Mode Selected")

    def lights_off(self):
        """The mode to turn all lights off for the huntsman system
        
        Attributes:
            bridge(str): bridge connection
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_index(int): the index of the led light strip found in the config file 
        """
        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("All Lights Off")

    def flat_field(self):
        """The flat_field mode for the huntsman system (in progress)
        
        Attributes:
            bridge(str): bridge connection
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_index(int): the index of the led light strip found in the config file  
        """
        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        self.bridge.lights[self.field_index].state(
            on=True, bri=250, hue=30000, sat=10)
        if self.verbose:
            print("Flat Field Mode Selected")
