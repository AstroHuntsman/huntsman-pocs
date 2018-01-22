from os import path
from qhue import Bridge, QhueException, create_new_username
from warnings import warn
from pocs.utils.config import load_config

class HueLights(object):
    """A Python interface for the lighting control system of the huntsman dome

        Creates a text file with stored username upon first connection to the bridge, will
        prompt the user to press the hue bridge button to connect for the fist time and writes
        the file to the working directory.
        Should a username already exist, the stored username is read and used to log into the
        bridge automatically.
        If a new username cannot be saved, and error message will be sent to the user. At this point
        manual login may be nessesary.

    Attributes:
        hue_ip(int): the ip address of the hue bridge.
        led_index(int): the index of the led light strip found in the config file
        desk_index(int): the index of the desk lamp found in config file
        flat_index(int): the index of the flat field light that will eventually be addd to the config file
        username_file_path(str): the file path of the text file that will be saved containing the current username
        verbose(bool): can be set to True or False to provide extra info if needed
        config: instance of the load_config class used to load configuration information from the configuration yaml file
        bridge(str): bridge connection
        light_states(str): Allowed light states in yaml file
    """

    def __init__(self):
        """Automatic login to the hue bridge using a stored username"""

        lights_config_path = '/Users/SC09015/Desktop/Astro/Code/huntsman-pocs/conf_files/set_lights.yaml'
        self.config = load_config(lights_config_path)
        self.hue_ip = self.config['hue_lights']['hue_ip']
        self.username_file_path = self.config['hue_lights']['username_file_path']
        self.led_index = self.config['hue_lights']['index']['led']
        self.desk_index = self.config['hue_lights']['index']['desk']
        self.flat_index = self.config['hue_lights']['index']['flat']
        self.verbose = False
        self.light_states = ('observing', 'observing_bright', 'bright', 'off', 'flats')

        if not path.exists(self.username_file_path):
            try:
                username = create_new_username(self.hue_ip)
            except QhueException as err:
                warn("Cannot create new username: {}".format(err))
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

    def get_bridge_index(self):
        """Used to return the index of each of the devices connected to the bridge should a factory reset occur

        Attributes:
            lights: instance of the qhue lights class
        """
        lights = self.bridge.lights()
        for num, info in lights.items():
            info = print("{:10} {}".format(info['name'], num))
            print(info)

    def set_state(self, state):
        """ Used to set the lighting state in the dome

        Atributes:
            state: can be set to 'observing', 'observing_bright', 'bright', 'off' or 'flats' depending on what light state is required
            bridge(str): bridge connection
            config: instance of the load_config class used to load configuration information from the configuration yaml file
            led_index(int): the index of the led light strip found in the config file
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_state: defines the brightness, state, hue and saturation of the led strip
            desk_state: defines the brightness, state, hue and saturation of the desk lamp
            flat_state: defines the brightness, state, hue and saturation of the flat field lamp
            light_states(str): Allowed light states in yaml file
        """
        
        if state not in self.lights_states:
            raise ValueError("State chosen is not recognised")
        led_state = self.config['states'][state]['led']
        desk_state = self.config['states'][state]['desk']
        flat_state = self.config['states'][state]['flat_field']
        self.bridge.lights[self.led_index].state(led_state)
        self.bridge.lights[self.desk_index].state(desk_state)
        self.bridge.lights[self.flat_index].state(flat_state)
