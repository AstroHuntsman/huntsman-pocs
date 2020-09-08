#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import time

from huntsman.pocs.utils import load_config

WINDOWS = ["main-control",
           "shutter-and-weather",
           "camera-servers",
           "camera-logs",
           "dome-control",
           "data managment"]

POCS_STARTUP = ["from pocs.mount import create_mount_from_config",
                "from pocs.scheduler import create_scheduler_from_config",
                "from huntsman.pocs.camera import create_cameras_from_config",
                "from huntsman.pocs.observatory import HuntsmanObservatory",
                "from pocs.core import POCS",
                "from huntsman.pocs.utils import load_config",
                "config = load_config",
                "cameras = create_cameras_from_config",
                "mount = create_mount_from_config(config)",
                "mount.initialize()",
                "scheduler = create_scheduler_from_config(config)",
                "observatory = HuntsmanObservatory(cameras=cameras, "
                "mount=mount, scheduler=scheduler, with_autoguider=True,"
                " take_flats=True",
                "pocs = POCS(observatory, simulator=['power','weather']",
                "#pocs.initialize()",
                "#pocs.run()"]

DOME_SHUTTER_STARTUP = ["from huntsman.pocs.dome.musca import HuntsmanDome",
                        "from huntsman.pocs.utils import load_config",
                        "config = load_config()",
                        "dome = HuntsmanDome(config=config)",
                        "dome.status()"
                        "#dome.open()"]

WEATHER_STARTUP = ["cd $PANDIR/my-aag-weather",
                   "docker-compose up"]


def new_window(window_name):
    """Create a new window in a byobu session and give it a name.

    Parameters
    ----------
    window_name : str
        Name for the new byobu window.

    """
    subprocess.call(f"byobu new-window", shell=True)
    subprocess.call(f"byobu rename-window '{window_name}'", shell=True)
    return


def send_command_to_pane(cmd, pane):
    """Send a command to selected pane within the current byobu window.

    Parameters
    ----------
    cmd : str
        The command to send to the selected pane.
    pane_num : int
        The index of the target pane.

    """
    subprocess.call(f"byobu select-pane -t {pane}", shell=True)
    subprocess.call(f"byobu send-keys '{cmd}'", shell=True)
    subprocess.call(f"byobu send-keys Enter", shell=True)
    return


def clear_current_pane():
    """Clear the contents of the current pane in focus.

    """
    # clear the pane
    subprocess.call(f"byobu send-keys Enter", shell=True)
    subprocess.call(f"byobu send-keys clear", shell=True)
    subprocess.call(f"byobu send-keys Enter", shell=True)
    return


def select_window(window_name, pane=0, session_name="1-Huntsman-Control"):
    """Select a window, as well as the pane from a given byobu session.

    Parameters
    ----------
    window_name : str
        Byobu window name.
    pane : int
        The index of the target pane.
    session_name : str
        Name of the byobu session containing the desired window.

    """
    subprocess.call(
        f"byobu select-window -t '{session_name}':'{window_name}'", shell=True)
    subprocess.call(f"byobu select-pane -t {pane}", shell=True)
    return


def create_12_pane_window(window_name, session_name="1-Huntsman-Control"):
    """Create a 4 by 3 pane, equally tiled byobu window.

    Parameters
    ----------
    window_name : str
        Byobu window name.
    session_name : str
        Name of the byobu session containing the desired window.

    """
    # start by splitting horizontally
    select_window(window_name, session_name=session_name)
    subprocess.call("byobu split-window -h", shell=True)
    subprocess.call("byobu split-window -h", shell=True)
    subprocess.call("byobu select-layout even-horizontal", shell=True)

    # Now split each side into 5 panes to get 10 panes in total
    subprocess.call("byobu select-pane -t 0", shell=True)
    for _ in range(3):
        subprocess.call("byobu split-window -v", shell=True)

    subprocess.call("byobu select-pane -t 4", shell=True)

    for _ in range(3):
        subprocess.call("byobu split-window -v", shell=True)

    subprocess.call("byobu select-pane -t 8", shell=True)

    for _ in range(3):
        subprocess.call("byobu split-window -v", shell=True)

    subprocess.call("byobu select-layout tiled", shell=True)


def setup_session(session_name="1-Huntsman-Control", windows=['']):
    """Create a new byobu session and populate desired windows.

    Parameters
    ----------
    session_name : str
        Name of the byobu session containing the desired window.
    windows : list of str
        List of byobu window names.

    """
    # subprocess.call(f"byobu new-session -d -s '{session_name}'", shell=True)
    subprocess.call(f"byobu new-session -d -s'{session_name}'", shell=True)
    for window in windows:
        new_window(window)
    select_window(windows[0])
    return


def setup_main_control_window(cmd_prefix='#'):
    """Function that automates the setup of the main control window.

    Parameters
    ----------
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    # setup the main-control window
    select_window(WINDOWS[0])
    # Select default pane. Probably an unnecessary line of code
    subprocess.call(f"byobu select-pane -t 0", shell=True)
    # split window hoirzontaly
    subprocess.call(f"byobu split-window -h", shell=True)
    # select pane 0
    subprocess.call(f"byobu select-pane -t 0", shell=True)
    # split selected pane vertically
    subprocess.call(f"byobu split-window -v", shell=True)
    # select the top pane
    subprocess.call(f"byobu select-pane -t 0", shell=True)
    # split top pane vertically again
    subprocess.call(f"byobu split-window -v", shell=True)
    # select the top pane
    subprocess.call(f"byobu select-pane -t 0", shell=True)

    clear_current_pane()
    # Now run the necessary commands in each pane
    send_command_to_pane(
        cmd_prefix + '$HUNTSMAN_POCS/scripts/pyro_name_server.py', 0)

    send_command_to_pane(
        cmd_prefix + 'python $HUNTSMAN_POCS/scripts/start_config_server.py', 1)

    send_command_to_pane(f'ipython', 2)

    for cmd in POCS_STARTUP:
        send_command_to_pane(cmd_prefix + cmd, 2)
        # issues occur without small pause between commands, unsure why
        time.sleep(0.01)

    send_command_to_pane(
        cmd_prefix + 'grc tail -F -n 1000 $PANDIR/logs/ipython-all.log', 3)
    return


def setup_shutter_weather_window(cmd_prefix='#'):
    """Function that automates the setup of the shutter and weather window.

    Parameters
    ----------
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(WINDOWS[1])
    # split window horizontally
    subprocess.call("byobu split-window -h", shell=True)
    select_window(WINDOWS[1], pane=0)
    # split left plane vertically
    subprocess.call("byobu split-window -v", shell=True)
    select_window(WINDOWS[1], pane=0)
    clear_current_pane()
    # pair control computer to Musca/TinyOS bluetooth device
    send_command_to_pane('sudo rfcomm connect rfcomm0 20:13:11:05:17:32', 0)
    # NB above command will prompt for password
    send_command_to_pane('password', 0)
    # start ipython session in panel 1 for controlling shutter
    send_command_to_pane('ipython', 1)
    for cmd in DOME_SHUTTER_STARTUP:
        send_command_to_pane(cmd_prefix + cmd, 1)
        time.sleep(0.1)
    # select right side pane and split vertically
    select_window(WINDOWS[1], pane=2)
    subprocess.call("byobu split-window -v", shell=True)
    for cmd in WEATHER_STARTUP:
        send_command_to_pane(cmd_prefix + cmd, 2)
    send_command_to_pane(
        cmd_prefix + 'http :5000/latest.json', 3)
    return


def setup_camera_server_window(config, cmd_prefix='#'):
    """Function that automates the setup of the camera servers window.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing device info.
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(WINDOWS[2])
    # create a 4x3 pane layout to accomodate all 10 cameras
    create_12_pane_window(WINDOWS[2])
    select_window(WINDOWS[2], pane=0)
    clear_current_pane()
    # config has keys dict_keys(['messaging,'control','ip1','ip2'...])
    for pane, ip in enumerate(list(config.keys())[2:]):
        select_window(WINDOWS[2], pane=pane)
        cmd1 = cmd_prefix + f"ssh huntsman@{ip}"
        # TODO, setup ssh keys so password isnt required
        cmd2 = cmd_prefix + "password"
        cmd3 = cmd_prefix + "$HUNTSMAN_POCS/scripts/run_device_container.sh"
        send_command_to_pane(cmd1, pane)
        send_command_to_pane(cmd2, pane)
        send_command_to_pane(cmd3, pane)
    return


def setup_camera_logs_window(config, cmd_prefix='#'):
    """Function that automates the setup of the camera logs window.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing device info.
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(WINDOWS[3])
    # create a 4x3 pane layout to accomodate all 10 cameras
    create_12_pane_window(WINDOWS[3])
    select_window(WINDOWS[3], pane=0)
    clear_current_pane()
    for pane, ip in enumerate(list(config.keys())[2:]):
        select_window(WINDOWS[3], pane=pane)
        cmd1 = cmd_prefix + f"ssh huntsman@{ip}"
        # TODO, setup ssh keys so password isnt required
        cmd2 = cmd_prefix + "password"
        cmd3 = cmd_prefix + "grc tail -F -n 1000 $PANDIR/"\
            "logs/pyro_camera_server.py-all.log"
        send_command_to_pane(cmd1, pane)
        send_command_to_pane(cmd2, pane)
        send_command_to_pane(cmd3, pane)
    return


def setup_dome_controller_log_window(cmd_prefix='#'):
    """Function that automates the setup of the dome controller log window.

    Parameters
    ----------
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(WINDOWS[4], pane=0)
    # ssh into domepi and display the server log
    cmd1 = cmd_prefix + "ssh huntsman@192.168.80.110"
    cmd2 = cmd_prefix + \
        "grc tail -F -n 1000 ~/huntsman-dome/domehunter/"\
        "logs/server_log_yyyy_mm_dd.log"
    send_command_to_pane(cmd1, 0)
    send_command_to_pane(cmd2, 0)
    return


def setup_data_management_window(cmd_prefix='#'):
    """Function that automates the setup of the data management window

    Parameters
    ----------
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(WINDOWS[5], pane=0)
    subprocess.call("byobu split-window -h", shell=True)
    return


if __name__ == "__main__":
    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--no_action',
                        help="Comment out all commands to prevent execution.",
                        action="store_const",
                        const='#',
                        default='')
    parser.add_argument('-c', '--config',
                        help="Specify the device info yaml config to use.",
                        action="store",
                        default='device_info_local_28_02_2020')

    args = parser.parse_args()

    config = load_config(config_files=args.config)
    if not bool(config):
        sys.exit("Loaded config is empty, exiting.")

    session_name = "1-Huntsman-Control"

    print("Setting up session windows")
    setup_session(session_name="1-Huntsman-Control", windows=WINDOWS)

    print("Setting up window (1/6) [main control]")
    setup_main_control_window(cmd_prefix=args.no_action)

    print("Setting up window (2/6) [weather monitoring]")
    setup_shutter_weather_window(cmd_prefix=args.no_action)

    print("Setting up window (3/6) [camera server]")
    setup_camera_server_window(config, cmd_prefix=args.no_action)

    print("Setting up window (4/6) [camera log]")
    setup_camera_logs_window(config, cmd_prefix=args.no_action)

    print("Setting up window (5/6) [dome control]")
    setup_dome_controller_log_window(cmd_prefix=args.no_action)

    print("Setting up window (6/6) [data management]")
    setup_data_management_window(cmd_prefix=args.no_action)

    select_window(WINDOWS[0], pane=0)
    subprocess.call(f"byobu attach -t {session_name}", shell=True)
