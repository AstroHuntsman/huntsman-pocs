import yaml

from os import path
from qhue import Bridge, QhueException, create_new_username

# note, light 5 can be 'uncommented' once installed, or causes problems
# using currently

class Hue_Lights(object):

    def __init__(self, verbose = False):

        # Find the yaml file and load the config parameters

        yamlf = "/Users/SC09015/Desktop/Astro/Code/huntsman-pocs/conf_files/set_lights.yaml"
        with open(yamlf, 'r') as yml:

            try:
                newyml = (yaml.load(yml))
                self.hue_ip = newyml['hue_lights'][0]['hue_ip']
                self.file_path = newyml['hue_lights'][1]['file_path']
                self.led_index = newyml['hue_lights'][2]['index']['led_index']
                self.desk_index = newyml['hue_lights'][2]['index']['desk_index']
                self.flat_index = newyml['hue_lights'][2]['index']['flat_index']

            except yaml.YAMLError as error:
                print(error)

        # If the file_path doesn't exist for a username, then create a new one
        # by pushing bridge button

        if not path.exists(self.file_path):

            try:
                username = create_new_username(self.hue_ip)

            except QhueException as err:
                print("Cannot create new username: {}".format(err))

            with open(self.file_path, "w") as cred_file:
                cred_file.write(username)

                if verbose:
                    print("Your hue username", username, "was created")

        else:

            with open(self.file_path, "r") as cred_file:
                username = cred_file.read()

                if verbose:
                    print("Login with username", username, "successful")

        # Bridge connection can be called at any time from here

        self.bridge = Bridge(self.hue_ip, username)

    def get_username(self):

        with open(self.file_path, 'r') as user:

            try:
                username = user.read()

            except BaseException:
                print("Username cannot be found")

                out = print(username)
        return(out)

    def get_index(self):

        lights = self.bridge.lights()

        for num, info in lights.items():

            info = print("{:10} {}".format(info['name'], num))

        return(info)

    def observing_mode(self, verbose=False):

        self.bridge.lights[self.led_index].state(on=True, bri=100, hue=50, sat=250)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)
        if verbose:
            print("Observing Mode Selected")

    def observing_bright_mode(self, verbose=False):

        self.bridge.lights[self.led_index].state(on=True, bri=250, hue=100, sat=250)
        self.bridge.lights[self.desk_index].state(on=True, bri=250, hue=30000, sat=20)
        #self.bridge.lights[self.field_index].state(on = False)

        if verbose:

            print("Observing Bright Mode Selected")

    def bright_mode(self, verbose=False):

        self.bridge.lights[self.led_index].state(on=True, bri=250, hue=30000, sat=10)
        self.bridge.lights[self.desk_index].state(on=True, bri=250, hue=30000, sat=10)
        #self.bridge.lights[self.field_index].state(on = False)

        if verbose:

            print("Bright Mode Selected")

    def lights_off(self, verbose=False):

        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        #self.bridge.lights[self.field_index].state(on = False)

        if verbose:

            print("All Lights Off")

    def flat_field(self, verbose=False):

        self.bridge.lights[self.led_index].state(on=False)
        self.bridge.lights[self.desk_index].state(on=False)
        self.bridge.lights[self.field_index].state(on=True, bri=250, hue=30000, sat=10)

        if verbose:

            print("Flat Field Mode Selected")
