import yaml

from os import path
from qhue import Bridge, QhueException, create_new_username

class Hue_Lights(object):

    def __init__(self):

        # Find the yaml file and load the config parameters
        # How to deal with this? File paths need to be set up in some sort of
        # config file?
        yamlf = "/Users/SC09015/Desktop/Astro/Code/huntsman-pocs/conf_files/set_lights.yaml"
        with open(yamlf, 'r') as yml:
            try:
                newyml = (yaml.load(yml))
                self.hue_ip = newyml['hue_lights'][0]['hue_ip']
                self.file_path = newyml['hue_lights'][1]['file_path']
                self.led_index = newyml['hue_lights'][2]['index']['led_index']
                self.desk_index = newyml['hue_lights'][2]['index']['desk_index']
                self.flat_index = newyml['hue_lights'][2]['index']['flat_index']
                self.verbose = False
            except yaml.YAMLError as error:
                print(error)

    def login(self):

        if not path.exists(self.file_path):
            try:
                username = create_new_username(self.hue_ip)
            except QhueException as err:
                print("Cannot create new username: {}".format(err))
            with open(self.file_path, "w") as cred_file:
                cred_file.write(username)
                if self.verbose:
                    print("Your hue username", username, "was created")
        else:
            with open(self.file_path, "r") as cred_file:
                username = cred_file.read()
                if self.verbose:
                    print("Login with username", username, "successful")

        self.bridge = Bridge(self.hue_ip, username)

        # Bridge connection can be called at any time from here
        # The problem here is, every time you attempt to create an instance of the class,
        # you will get that the button needs to be pushed, if you are not already logged into
        # the bridge. This is not good? - changed this?

    def get_username(self):
        with open(self.file_path, 'r') as user:
            if not path.exists(self.file_path):
                print("Username cannot be found")
            else:
                username = user.read()
        return(print(username))

    def get_index(self):
        lights = self.bridge.lights()
        for num, info in lights.items():
            info = print("{:10} {}".format(info['name'], num))
        return(info)

    def observing_mode(self):
        self.bridge.lights[self.led_index].state(
            on=True, bri=100, hue=50, sat=250)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Observing Mode Selected")

    def observing_bright_mode(self):
        self.bridge.lights[self.led_index].state(
            on=True, bri=250, hue=100, sat=250)
        self.bridge.lights[self.desk_index].state(
            on=True, bri=250, hue=30000, sat=20)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Observing Bright Mode Selected")

    def bright_mode(self):
        self.bridge.lights[self.led_index].state(
            on=True, bri=250, hue=30000, sat=10)
        self.bridge.lights[self.desk_index].state(
            on=True, bri=250, hue=30000, sat=10)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("Bright Mode Selected")

    def lights_off(self):
        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)
        if self.verbose:
            print("All Lights Off")

    def flat_field(self):
        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        self.bridge.lights[self.field_index].state(
            on=True, bri=250, hue=30000, sat=10)
        if self.verbose:
            print("Flat Field Mode Selected")
