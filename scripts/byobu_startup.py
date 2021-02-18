#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import time


WINDOW_CMDS = {"DOCKER": ["cd ${PANDIR}/huntsman-config && git pull",
                          "cd ${HUNTSMAN_POCS}/docker && docker-compose down",
                          "docker-compose pull",
                          "docker-compose up"],
               "PYTHON": ["docker exec -it pocs-control /bin/bash",
                          "ipython",
                          "from huntsman.pocs.utils.huntsman import create_huntsman_pocs",
                          "pocs = create_huntsman_pocs(with_dome=True, simulators=['power'])",
                          "#pocs.run()"],
               "LOGS": ["cd $PANLOG && tail -F -n 1000 panoptes.log"],
               "PILOGS": ["cd $PANLOG && tail -F -n 1000 huntsman.log"],
               "WEATHER": ["cd $PANDIR/huntsman-environment-monitor/src/huntsmanenv",
                           "python run_dash.py"],
               "SHUTTER": ["#docker exec -it -u huntsman pocs-config-server /bin/bash",
                           "#ipython",
                           "#from huntsman.pocs.dome import create_dome_from_config",
                           "#dome = create_dome_from_config()",
                           "#dome.status"]}


def call_byobu(cmd, screen_cmd='byobu', shell=True, executable='/bin/bash'):
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


def setup_session(session_name="1-Huntsman-Control", windows=None):
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


def setup_simple_window(window_name, cmd_list, cmd_prefix='#'):
    """Function to run through a list of commands in a simple
    byobu window (ie no split panes etc)

    Args:
        window_index (str): Name of the window to setup
        cmd_list (list): List of commands to run within window
        cmd_prefix (str, optional): [description]. Defaults to '#'.
    """
    # select desired window
    select_window(window_name)

    for cmd in WINDOW_CMDS[window_name]:
        send_command_to_pane(cmd_prefix + cmd, 0)
        # issues occur without small pause between commands, unsure why
        time.sleep(0.01)
    return


def setup_pilogs_window(window_name='PILOGS', cmd_prefix='#'):
    """Function that automates the setup of the camera logs window.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing device info.
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(window_name)
    # create a 4x3 pane layout to accomodate all 10 cameras
    create_12_pane_window(window_name)
    select_window(window_name, pane=0)
    clear_current_pane()
    for i in range(12):
        select_window(window_name, pane=i)
        # use the aliases defined in ~/.bashrc to ssh into the pis
        cmd1 = cmd_prefix + f"pi{i}"
        cmd3 = cmd_prefix + WINDOW_CMDS[window_name][0]
        send_command_to_pane(cmd1, i)
        send_command_to_pane(cmd3, i)
    return


def setup_shutter_window(window_name="SHUTTER", cmd_prefix='#'):
    """Function that automates the setup of the PILOGS window.

    Parameters
    ----------
    window_name : str
        Name of the pilogs window.
    cmd_prefix : str
        The prefix to prepend to any shell commands (ie to comment them out).

    """
    select_window(window_name)
    # connect to the pocs-config-server container to control the shutter
    for cmd in WINDOW_CMDS[window_name]:
        send_command_to_pane(cmd_prefix+cmd, 0)
    return


if __name__ == "__main__":
    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--no_action',
                        help="Comment out all commands to prevent execution.",
                        action="store_const",
                        const='#',
                        default='')

    args = parser.parse_args()

    session_name = "1-Huntsman-Control"

    print("Setting up session windows")
    windows = list(WINDOW_CMDS.keys())
    setup_session(session_name="1-Huntsman-Control", windows=windows)

    print(f"Setting up window (1/{len(windows)}) [{windows[0]}]")
    setup_simple_window(windows[0], WINDOW_CMDS[windows[0]], cmd_prefix=args.no_action)

    print(f"Setting up window (2/{len(windows)}) [{windows[1]}]")
    setup_simple_window(windows[1], WINDOW_CMDS[windows[1]], cmd_prefix=args.no_action)

    print(f"Setting up window (3/{len(windows)}) [{windows[2]}]")
    setup_simple_window(windows[2], WINDOW_CMDS[windows[2]], cmd_prefix=args.no_action)

    print(f"Setting up window (4/{len(windows)}) [{windows[3]}]")
    setup_pilogs_window(windows[3], cmd_prefix=args.no_action)

    print(f"Setting up window (5/{len(windows)}) [{windows[4]}]")
    setup_simple_window(windows[4], WINDOW_CMDS[windows[4]], cmd_prefix=args.no_action)

    print(f"Setting up window (6/{len(windows)}) [{windows[5]}]")
    setup_shutter_window(window_name="SHUTTER", cmd_prefix=args.no_action)

    select_window(windows[0], pane=0)
    subprocess.call(f"byobu attach -t {session_name}", shell=True)
