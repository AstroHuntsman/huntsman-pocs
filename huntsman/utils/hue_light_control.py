from os import path
from qhue import Bridge, QhueException, create_new_username

# note, light 5 can be 'uncommented' once installed, or causes problems
# using currently


def login(
        hue_ip="10.88.21.10",
        file_path="hue_username.txt",
        verbose=False):
    """Automatic connection to the hue bridge using a stored username.

        Creates a text file with stored username upon first connection to the bridge, will
        prompt the user to press the hue bridge button to connect for the fist time and writes
        the file to the central directory.

        Should a username already exist, the stored username is read and used to log into the
        bridge automatically.

        If a new username cannot be saved, and error message will be sent to the user. At this point
        manual login may be nessesary.

    Args:

        hue_ip (int): the ip address of the hue bridge. Set by default to "10.88.21.10"

        file_path (str): the file name of the text file that will be saved containing the current username

    Returns:

        bridge (string): bridge connection

    """

    if not path.exists(file_path):

        try:
            username = create_new_username(hue_ip)

        except QhueException as err:
            print("Cannot create new username: {}".format(err))

        with open(file_path, "w") as cred_file:
            cred_file.write(username)

            if verbose:
                print("Your hue username", username, "was created")

    else:

        with open(file_path, "r") as cred_file:
            username = cred_file.read()

            if verbose:
                print("Login with username", username, "successful")

    bridge = Bridge(hue_ip, username)

    return(bridge)


def find_hue_light_index(bridge):
    """Check the index of any hue light connected to the bridge

    Args:

        bridge (str): bridge connection, i.e bridge = automatic_login_phillips_hue()

    Returns:

        info (int): Returns the index of each hue device connected to the bridge

    """

    lights = bridge.lights()

    for num, info in lights.items():

        info = print("{:10} {}".format(info['name'], num))

    return(info)


def hue_observing_mode(bridge, led_index, desk_index, verbose=False):
    """Low red light for observing. Desk lamp off

    Args:

        bridge (str): connection to the bridge, i.e b = automatic_login_phillips_hue()

        led_index (int): the unique index of the hue LED strip, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1

        desk_index (int): index of desk lamp. At present, = 4

    """

    bridge.lights[led_index].state(on=True, bri=100, hue=50, sat=250)
    bridge.lights[desk_index].state(on=False)
    #b.lights[field_index].state(on = False)

    if verbose:

        print("Observing Mode Selected")


def hue_observing_bright_mode(bridge, led_index, desk_index, verbose=False):
    """Bright red light for observing and viewing. Desk lamp on

    Args:

        bridge (str): Connection to the bridge, i.e bridge = automatic_login_phillips_hue()

        led_index (int): the unique index of the hue LED strip, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1

        desk_index (int): index of desk lamp. At present, = 4

    """

    bridge.lights[led_index].state(on=True, bri=250, hue=100, sat=250)
    bridge.lights[desk_index].state(on=True, bri=250, hue=30000, sat=20)
    #b.lights[field_index].state(on = False)

    if verbose:

        print("Observing Bright Mode Selected")


def hue_bright_mode(bridge, led_index, desk_index, verbose=False):
    """Bright mode for both LED strip and desk lamp for desk cam to monitor dome

    Args:

        bridge (str): connection to the bridge, i.e b = automatic_login_phillips_hue()

        led_index (int): the unique index of the hue LED stip, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1

        desk_index (int): index of desk lamp. At present, = 4

    """

    bridge.lights[led_index].state(on=True, bri=250, hue=30000, sat=10)
    bridge.lights[desk_index].state(on=True, bri=250, hue=30000, sat=10)
    #b.lights[field_index].state(on = False)

    if verbose:

        print("Bright Mode Selected")


def hue_lights_off(bridge, led_index, desk_index, verbose=False):
    """Turns all lights off in the dome

    Inputs:

        bridge (str): connection to the bridge, i.e bridge = automatic_login_phillips_hue()

        led_index (int): the unique index of the hue LED strip, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1

        desk_index (int): index of desk lamp. At present, = 4

    """

    bridge.lights[led_index].state(on=False)
    bridge.lights[desk_index].state(on=False)
    #bridge.lights[field_index].state(on = False)

    if verbose:

        print("All Lights Off")


def hue_flat_field(bridge, led_index, desk_index, field_index, verbose=False):
    """Flat field function for a 3rd lamp, turns off other lights

    Args:

        bridge (str): connection to the bridge, i.e b = automatic_login_phillips_hue()

        led_index (int): the unique index of the hue LED strip, enter as string e.g '1'
                   can be found using find_hue_index. At present, = 1

        desk_index (int): index of desk lamp. At present, = 4

        field_index (int): index of flat field lamp. To be added to the system.
                     will be allocated index 5

    """

    bridge.lights[led_index].state(on=False)
    bridge.lights[desk_index].state(on=False)
    bridge.lights[field_index].state(on=True, bri=250, hue=30000, sat=10)

    if verbose:

        print("Flat Field Mode Selected")
