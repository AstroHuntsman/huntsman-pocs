#!/usr/bin/env python3

import argparse
import subprocess
import sys
import time

from huntsman.pocs.utils import load_config

WINDOWS = ["main-control",
           "huntsman-pocs-servers"
           "dome-shutter"
           "weather",
           "camera-services"
           "camera-logs",
           "dome-control"]

DOME_SHUTTER_STARTUP = ["from huntsman.pocs.dome.musca import HuntsmanDome",
                        "from huntsman.pocs.utils import load_config",
                        "config = load_config()",
                        "dome = HuntsmanDome(config=config)",
                        "dome.status()"]

WEATHER_STARTUP = ["cd ${PANDIR}/my-aag-weather",
                   "docker-compose down"
                   "docker-compose up"]


def call_byobu(cmd, screen_cmd='byobu', shell=True, executable='/bin/zsh'):
    """Calls the given command within a byobu screen session.

    Parameters
    ----------
    cmd : str
        tmux scripting command to run.
    screen_cmd : str
        Default tmux manager is byobu but if desired the cmd can be run using
        just tmux instead of byobu.
    shell : bool
        This argument sets whether to run the subprocess call cmd through a
        shell, as opposed treating the input command as the name of an
        executable to be run.
    executable : sh
        The path to the shell executable you wish to use.

    """
    run_cmd = f'{screen_cmd} {cmd}'
    subprocess.call(run_cmd, shell=shell, executable=executable)


def new_window(window_name):
    """Create a new window in a byobu session and give it a name.

    Parameters
    ----------
    window_name : str
        Name for the new byobu window.

    """
    call_byobu("new-window")
    rename_window(window_name)
    return


def rename_window(window_name):
    """Rename current byobu window.

    Parameters
    ----------
    window_name : type
        Description of parameter `window_name`.

    """
    call_byobu(f"rename-window '{window_name}'")
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
    call_byobu(f"select-pane -t {pane}")
    call_byobu(f"send-keys '{cmd}'")
    call_byobu(f"send-keys Enter")
    return


def clear_current_pane():
    """Clear the contents of the current pane in focus.

    """
    # clear the pane
    call_byobu(f"send-keys Enter")
    call_byobu(f"send-keys clear")
    call_byobu(f"send-keys Enter")
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
    call_byobu(f"select-window -t '{session_name}':'{window_name}'")
    call_byobu(f"select-pane -t {pane}")
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
    call_byobu(f"split-window -h")
    call_byobu(f"split-window -h")
    call_byobu(f"select-layout even-horizontal")

    # Now split each side into 5 panes to get 10 panes in total
    call_byobu(f"select-pane -t 0")
    for _ in range(3):
        call_byobu(f"split-window -v")

    call_byobu(f"select-pane -t 4")

    for _ in range(3):
        call_byobu(f"split-window -v")

    call_byobu(f"select-pane -t 8")

    for _ in range(3):
        call_byobu(f"split-window -v")

    call_byobu(f"select-layout tiled")


def setup_session(session_name="huntsman-control", windows=None):
    """Create a new byobu session and populate desired windows.

    Parameters
    ----------
    session_name : str
        Name of the byobu session containing the desired window.
    windows : list of str
        List of byobu window names.
    """
    windows = windows or list()
    call_byobu(f"new-session -d -s '{session_name}'")
    # first we will rename the existing window
    rename_window(windows[0])
    # now iterate through list of desired window names and create them
    for window in windows[1:]:
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
    select_window("main_control")
    # Select default pane. Probably an unnecessary line of code
    call_byobu(f"select-pane -t 0")
    # split window hoirzontaly
    call_byobu(f"split-window -h")
    # select pane 0
    call_byobu(f"select-pane -t 0")
    # split selected pane vertically
    call_byobu(f"split-window -v")
    # select the top pane
    call_byobu(f"select-pane -t 0")
    # split top pane vertically again
    call_byobu(f"split-window -v")
    # select the top pane
    call_byobu(f"select-pane -t 0")

    clear_current_pane()
    # Now run the necessary commands in each pane
    send_command_to_pane(
        cmd_prefix + '${HUNTSMAN_POCS}/scripts/pyro_name_server.py', 0)

    send_command_to_pane(
        cmd_prefix + 'python ${HUNTSMAN_POCS}/scripts/start_config_server.py', 1)

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
    call_byobu(f"split-window -h")
    select_window(WINDOWS[1], pane=0)
    # split left plane vertically
    call_byobu(f"split-window -v")
    select_window(WINDOWS[1], pane=0)
    clear_current_pane()
    # pair control computer to Musca/TinyOS bluetooth device
    send_command_to_pane('sudo rfcomm connect rfcomm0 20:13:11:05:17:32', 0)
    # NB above command will prompt for password
    # send_command_to_pane('password', 0)
    # start ipython session in panel 1 for controlling shutter
    send_command_to_pane('ipython', 1)
    for cmd in DOME_SHUTTER_STARTUP:
        send_command_to_pane(cmd_prefix + cmd, 1)
        time.sleep(0.1)
    # select right side pane and split vertically
    select_window(WINDOWS[1], pane=2)
    call_byobu(f"split-window -v")
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
        print(f'Setting up {pane} on {ip}')
        select_window(WINDOWS[2], pane=pane)
        cmd1 = cmd_prefix + f"ssh huntsman@{ip}"
        cmd3 = cmd_prefix + 'python "${HUNTSMAN_POCS}/scripts/run_device.py"'
        send_command_to_pane(cmd1, pane)
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
        cmd3 = cmd_prefix + "grc tail -F -n 1000 $PANDIR/logs/pyro_camera_server.py-all.log"
        send_command_to_pane(cmd1, pane)
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
    cmd2 = cmd_prefix + "grc tail -F -n 1000 ~/huntsman-dome/domehunter/"\
        "logs/server_log_yyyy_mm_dd.log"
    send_command_to_pane(cmd1, 0)
    send_command_to_pane(cmd2, 0)
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

    print("Setting up session windows")
    setup_session()

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
