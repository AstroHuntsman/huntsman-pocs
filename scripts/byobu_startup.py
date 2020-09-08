#!/usr/bin/env python3

import os
import subprocess
import time

from huntsman.pocs.utils import load_config

# subprocess.call(cmd, shell=True)

WINDOWS = ["main-control",
           "shutter-and-weather",
           "camera-servers",
           "camera-logs",
           "dome-control"]

POCS_STARTUP = ["from pocs.mount import create_mount_from_config",
                "from pocs.scheduler import create_scheduler_from_config",
                "from huntsman.camera import create_cameras_from_config",
                "from huntsman.observatory import HuntsmanObservatory",
                "from pocs.core import POCS",
                "from huntsman.utils import load_config",
                "config = load_config",
                "cameras = create_cameras_from_config",
                "mount = create_mount_from_config(config)",
                "mount.initialize()",
                "scheduler = create_scheduler_from_config(config)",
                "observatory = HuntsmanObservatory(cameras=cameras, mount=mount, scheduler=scheduler, with_autoguider=True, take_flats=True",
                "pocs = POCS(observatory, simulator=['power','weather']",
                "pocs.initialize()",
                "pocs.run()"]

DOME_SHUTTER_STARTUP = ["from huntsman.dome.musca import HuntsmanDome",
                        "from huntsman.utils import load_config",
                        "config = load_config()",
                        "dome = HuntsmanDome(config=config)",
                        "dome.status()"
                        "dome.open()"]

WEATHER_STARTUP = ["$POCS/bin/peas_shell",
                   "load_weather",
                   "start",
                   "last_reading weather"]


def new_window(window_name):
    subprocess.call("byobu new-window", shell=True)
    subprocess.call("byobu rename-window '{window_name}'", shell=True)


def send_command_to_pane(cmd, pane_num):
    subprocess.call("byobu select-pane -t {pane_num}", shell=True)
    subprocess.call("byobu send-keys '{cmd}'", shell=True)
    subprocess.call("byobu send-keys Enter", shell=True)


def select_window(window_name, session_name="1-Huntsman-Control"):
    subprocess.call(
        f"byobu select-window -t '{session_name}':'{window_name}'", shell=True)


def setup_session(session_name="1-Huntsman-Control", windows=['']):
    subprocess.call(f"byobu new-session -d -s '{session_name}'", shell=True)
    for window in windows:
        new_window(window)
    select_window(windows[0])


def setup_main_control_window(silent_mode=True):
    # setup the main-control window
    select_window(WINDOWS[0])
    # Select default pane. Probably an unnecessary line of code
    subprocess.call("byobu select-pane -t 0", shell=True)
    # split window hoirzontaly
    subprocess.call("byobu split-window -h", shell=True)
    # select pane 0
    subprocess.call("byobu select-pane -t 0", shell=True)
    # split selected pane vertically
    subprocess.call("byobu split-window -v", shell=True)
    # select the top pane
    subprocess.call("byobu select-pane -t 0", shell=True)
    # split top pane vertically again
    subprocess.call("byobu split-window -v", shell=True)
    # select the top pane
    subprocess.call("byobu select-pane -t 0", shell=True)

    # Now run the necessary commands in each pane
    cmd_prefix_py = ''
    cmd_prefix_sh = ''
    if silent_mode:
        cmd_prefix_py = '#'
        cmd_prefix_sh = 'echo '
    send_command_to_pane(
        cmd_prefix_sh + '$HUNTSMAN_POCS/scripts/pyro_name_server', 0)
    send_command_to_pane(
        cmd_prefix_sh + 'python $HUNTSMAN_POCS/scripts/start_config_server.py', 1)
    send_command_to_pane('ipython', 2)
    for cmd in POCS_STARTUP:
        send_command_to_pane(cmd_prefix_py + cmd, 2)
        time.sleep(0.1)
    send_command_to_pane(
        cmd_prefix + 'echo grc tail -F -n 1000 $PANDIR/logs/ipython-all.log', 3)


def setup_shutter_weather_window(silent_mode=True):
    cmd_prefix_py = ''
    cmd_prefix_sh = ''
    if silent_mode:
        cmd_prefix_py = '#'
        cmd_prefix_sh = 'echo '
    select_window(WINDOWS[1])
    subprocess.call("byobu split-window -h", shell=True)
    send_command_to_pane('ipython', 0)
    for cmd in DOME_SHUTTER_STARTUP:
        send_command_to_pane(cmd_prefix_py + cmd, 0)
        time.sleep(0.1)
    subprocess.call("select-pane -t 1", shell=True)
    subprocess.call("split-window -v", shell=True)
    # subprocess.call("select-pane -t 1", shell=True)
    for cmd in WEATHER_STARTUP:
        send_command_to_pane(cmd_prefix_sh + cmd, 1)
        time.sleep(0.1)
    send_command_to_pane(
        cmd_prefix_sh + 'grc tail -F $PANDIR/logs/peas_shell_all.log', 2)


def setup_camera_server_window(silent_mode=True):
    cmd_prefix_py = ''
    cmd_prefix_sh = ''
    if silent_mode:
        cmd_prefix_py = '#'
        cmd_prefix_sh = 'echo '
    select_window(WINDOWS[2])
    # start by splitting horizontally
    subprocess.call("byobu split-window -h", shell=True)
    # Now split each side into 5 panes to get 10 panes in total
    subprocess.call("byobu select-pane -t 0", shell=True)
    for _ in range(5):
        subprocess.call("byobu split-window -v", shell=True)
    return

    subprocess.call("byobu split-window -h", shell=True)
    # select pane 0
    subprocess.call("byobu select-pane -t 0", shell=True)
    # split selected pane vertically
    subprocess.call("byobu split-window -v", shell=True)


def setup_camera_logs_window(silent_mode=True):
    cmd_prefix_py = ''
    cmd_prefix_sh = ''
    if silent_mode:
        cmd_prefix_py = '#'
        cmd_prefix_sh = 'echo '
    select_window(WINDOWS[3])
    return


def setup_dome_control_window(silent_mode=True):
    cmd_prefix_py = ''
    cmd_prefix_sh = ''
    if silent_mode:
        cmd_prefix_py = '#'
        cmd_prefix_sh = 'echo '
    select_window(WINDOWS[4])
    return


if __name__ == "__main__":
    stemdir = '/home/fergus/Documents/REPOS/1HOME_PROJECTS/byobu-startup/'
    config = load_config(stemdir + 'device_info_local_28_02_2020.yaml')
    # check the number of cameras in the config
    num_cameras = len(config.keys()) - 2
    setup_session(session_name="1-Huntsman-Control", windows=WINDOWS)


# t='asdadasd'
#cmd = f"echo '{t}'"
#subprocess.call(cmd, shell=True)
# config.keys()
# config.items()
# for key, value in d.items():
# the device config has keys dict_keys(['messaging,'control','ip1','ip2'...])


# for each ip dict need; 'host', 'name' (replace with cam name?)

# ZWO camera with Birger focuser on Christopher:
# 192.168.80.140:
#   name: camera.zwo.0
#   host: 192.168.80.140
#   type: camera
#   directories:
#     base: /var/huntsman
#     images: images
#   camera:
#     model: zwo
#     timeout: 10
#     serial_number: "371d420013090900"
#     target_temperature: 0
#     gain: 100
#     focuser:
#       model: birger
#       port: '14284'
#       dev_node_pattern: '/dev/ttyUSB?'
#       initial_position: 21774
#       autofocus_keep_files: False
#       autofocus_range:
#         - 50
#         - 250
#       autofocus_step:
#         - 5
#         - 25
#       autofocus_seconds: 1
#       autofocus_size: 1500
#     filterwheel:
#       model: zwo
#       serial_number: 2
#       filter_names:
#         - 'blank'
#         - 'luminance'
#         - 'g_band'
#         - 'r_band'
#         - 'halpha'
#         - 's_II'
#         - 'empty'
