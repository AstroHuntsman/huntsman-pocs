import yaml
from qhue import Bridge, QhueException, create_new_username
from warnings import warn
from pocs.utils.config import load_config

class HueLights(object):
    """A Python interface for the lighting control system of the huntsman dome

        Adds a username to the 'set_lights' config file upon first connection to the bridge and will prompt the user to press the hue bridge button to connect for the first time.
        Should a username already exist, the stored username is read and used to log into the bridge automatically.
        If a new username cannot be created, an error message will be sent to the user. At this point manual login (press the blue button) or full reset may be nessesary.

    Attributes:
        hue_ip(str): the ip address of the hue bridge - please note, this must be manualy input into the set_lights.yaml file to avoid pushing to git hub
        led_index(int): the index of the led light strip found in the config file
        desk_index(int): the index of the desk lamp found in config file
        flat_index(int): the index of the flat field light that will eventually be addd to the config file
        hue_username(str): username used to log onto the brige, stored in the 'set_lights' config file
        verbose(bool): can be set to True or False to provide extra info if needed
        config: instance of the load_config class used to load configuration information from the configuration yaml file
        bridge(str): bridge connection
        light_states(str): allowed light states in yaml file
        config_directory(str): location of the config file
    """

    def __init__(self, info_verbose=False):
        """Automatic login to the hue bridge using a stored username"""

        self.config_directory = '/var/huntsman/huntsman-pocs/conf_files/set_lights.yaml'
        self.config = load_config(self.config_directory)
        self.hue_ip = self.config['hue_lights']['hue_ip']
        self.hue_username = self.config['hue_lights']['username']
        self.led_index = self.config['hue_lights']['bridge_index']['led']
        self.desk_index = self.config['hue_lights']['bridge_index']['desk']
        self.flat_index = self.config['hue_lights']['bridge_index']['flat']
        self.light_states = (
            'observing',
            'observing_bright',
            'bright',
            'all_off',
            'flats')
        if info_verbose:
            self.verbose = True
        else:
            self.verbose = False
        if self.hue_username is None:
            try:
                username = create_new_username(self.hue_ip)
            except QhueException as err:
                warn("Cannot create new username: {}".format(err))
                with open(self.config_directory) as file:
                    self.lights_info = yaml.load(file)
                    self.lights_info['hue_lights']['username'] = username
                with open(self.config_directory, 'w') as file:
                    yaml.dump(self.light_info, file)
            except FileNotFoundError:
                warn("Cannot find set_lights config file")
                if self.verbose:
                    print("Your hue username {} was created".format(username))
        else:
            if self.verbose:
                print("Login with username {} successful".format(username))
        self.bridge = Bridge(self.hue_ip, username)

    def get_bridge_index(self):
        """Used to print the index of each of the devices connected to the
        bridge should a factory reset occur

        Attributes:
            lights: instance of the qhue lights class
        """
        lights = self.bridge.lights()
        for num, info in lights.items():
            info = print("{:10} {}".format(info['name'], num))
            print(info)
        return info

    def set_state(self, state):
        """ Used to set the lighting state in the dome

        Atributes:
            state(str): can be set to 'observing', 'observing_bright', 'bright','all_off' or 'flats' depending on what light state is required
            bridge(str): bridge connection
            config: instance of the load_config class used to load configuration information from the configuration yaml file
            led_index(int): the index of the led light strip found in the config file
            desk_index(int): the index of the desk lamp found in config file
            flat_index(int): the index of the flat field light that will eventually be addd to the config file
            led_state: defines the brightness, state, hue and saturation of the led strip
            desk_state: defines the brightness, state, hue and saturation of the desk lamp
            flat_state: defines the brightness, state, hue and saturation of the flat field lamp
            light_states(str): allowed light states in yaml file
        """

        if state not in self.light_states:
            raise ValueError(("State chosen is not recognised, please use one of the following: {}").format(self.light_states))
        led_state = self.config['states'][state]['led']
        desk_state = self.config['states'][state]['desk']
        #flat_state = self.config['states'][state]['flat_field']
        self.bridge.lights[self.led_index].state(
            on=led_state['on'], bri=led_state['bri'], hue=led_state['hue'],
            sat=led_state['sat'])
        self.bridge.lights[self.desk_index].state(
            on=desk_state['on'], bri=desk_state['bri'], hue=desk_state['hue'],
            sat=desk_state['sat'])
        # self.brid.lights[self.flat_index].state(flat_state)
        if self.verbose:
            print("Lights have been set to {} mode".format(state))
