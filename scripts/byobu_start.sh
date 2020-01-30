#!/bin/bash

# Create new session.
SESSION_NAME=${1-Huntsman-Control)

byobu new-session -d -s "${SESSION_NAME}"

# To be able to actually see anything, you need to launch a terminal for the session
#gnome-terminal --full-screen -- byobu attach -t Huntsman-Control
gnome-terminal --window --maximize -- byobu attach -t "${SESSION_NAME}"

# Create required window
byobu new-window
byobu rename-window "main-control"
byobu new-window
byobu rename-window "shutter-and-weather"
byobu new-window
byobu rename-window "camera-servers"
byobu new-window
byobu rename-window "camera-logs"
byobu new-window
byobu rename-window "dome-control"
byobu select-window -t Huntsman-Control:"main-control"

# setup the main-control window
# Select default pane. Probably an unnecessary line of code
byobu select-pane -t 0
# split window hoirzontaly
byobu split-window -h
# select pane 0
byobu select-pane -t 0
# split selected pane vertically
byobu split-window -v
byobu select-pane -t 0
# run a command in selected pane, must end with 'Enter'
byobu send-keys "echo cd $HUNTSMAN_POCS"
byobu send-keys Enter
byobu send-keys "echo scripts/pyro_name_server.py"
byobu send-keys Enter
byobu select-pane -t 1
byobu send-keys "ipython"
byobu send-keys Enter
# pocs start up steps
pocsstart=("from pocs.mount import create_mount_from_config"
            "from pocs.scheduler import create_scheduler_from_config"
            "from huntsman.camera import create_cameras_from_config"
            "from huntsman.observatory import HuntsmanObservatory"
            "from pocs.core import POCS"
            "from huntsman.utils import load_config"
            "config = load_config"
            "cameras = create_cameras_from_config"
            "mount = create_mount_from_config(config)"
            "mount.initialize()"
            "scheduler = create_scheduler_from_config(config)"
            "observatory = HuntsmanObservatory(cameras=cameras, mount=mount, scheduler=scheduler, with_autoguider=True, take_flats=True"
            "pocs = POCS(observatory, simulator=['power','weather']"
            "pocs.initialize()"
            "pocs.run()")
for ((i = 0; i < ${#pocsstart[@]}; i++)); do
    # sending command through as a comment for testing purposes
    byobu send-keys "#[step ${i}] >${pocsstart[$i]}"
    byobu send-keys Enter
done
byobu select-pane -t 2
byobu send-keys "echo cd $PANLOG"
byobu send-keys Enter
byobu send-keys "echo grc tail -F -n 1000 ipython-all.log"
byobu send-keys Enter

# create shutter and weather window
byobu select-window -t Huntsman-Control:"shutter-and-weather"
byobu split-window -h
byobu select-pane -t 0
byobu send-keys "ipython"
byobu send-keys Enter
byobu send-keys "print('This is where shutter control happens')"
byobu send-keys Enter
byobu select-pane -t 1
byobu split-window -v
byobu select-pane -t 1
byobu send-keys "echo cd $POCS"
byobu send-keys Enter
byobu send-keys "echo bin/peas_shell"
byobu send-keys Enter
byobu send-keys "echo load_weather"
byobu send-keys Enter
byobu send-keys "echo start"
byobu send-keys Enter
byobu select-pane -t 2
byobu send-keys "echo PEAS LOGS GOES HERE"
byobu send-keys Enter

# create camera server window
byobu select-window -t Huntsman-Control:"camera-servers"
byobu split-window -h
byobu select-pane -t 0
byobu split-window -v
byobu split-window -v
byobu select-pane -t 3
byobu split-window -v
byobu split-window -v
# set layout to give equal spacing to each individual pane in the current window
byobu select-layout tiled
# now start all the camera servers
ipprefix="192.168.80."
ipsuffix=("140" "141" "143" "144" "145" "146")
for _pane in $(byobu list-panes -F '#P'); do
    # ssh into the pi
    byobu send-keys -t ${_pane} "echo ssh huntsman@$ipprefix${ipsuffix[${_pane}]}"
    byobu send-keys -t ${_pane} Enter
    # create a persistent byobu session on the pi
    byobu send-keys -t ${_pane} "echo byobu"
    byobu send-keys -t ${_pane} Enter
    # change to huntsman pocs directory
    byobu send-keys -t ${_pane} "echo cd $HUNTSMAN_POCS"
    byobu send-keys -t ${_pane} Enter
    # run camera server start up script
    byobu send-keys -t ${_pane} "echo scripts/pyro-camera-server.py"
    byobu send-keys -t ${_pane} Enter
done

# create camera server logs window
byobu select-window -t Huntsman-Control:"camera-logs"
byobu split-window -h
byobu select-pane -t 0
byobu split-window -v
byobu split-window -v
byobu select-pane -t 3
byobu split-window -v
byobu split-window -v
byobu select-layout tiled
# now start all the camera servers
for _pane in $(byobu list-panes -F '#P'); do
    # ssh into the pi
    byobu send-keys -t ${_pane} "echo ssh huntsman@$ipprefix${ipsuffix[${_pane}]}"
    byobu send-keys -t ${_pane} Enter
    # create a persistent byobu session on the pi
    byobu send-keys -t ${_pane} "echo byobu"
    byobu send-keys -t ${_pane} Enter
    # change to huntsman pocs directory
    byobu send-keys -t ${_pane} "echo cd $PANLOG"
    byobu send-keys -t ${_pane} Enter
    # run camera server start up script
    byobu send-keys -t ${_pane} "echo grc tail -F -n 1000 pyro_camera_server.py-all.log"
    byobu send-keys -t ${_pane} Enter
done

# create dome control window
byobu select-window -t Huntsman-Control:"dome-control"
byobu split-window -h
# start up dome control server
byobu select-pane -t 0
byobu send-keys "echo cd ~/huntsman-dome/domehunter/gRPC-server/"
byobu send-keys Enter
byobu send-keys "echo python huntsman_dome_server.py -r"
byobu send-keys Enter
# set up dome control log
byobu select-pane -t 1
byobu send-keys "echo cd ~/huntsman-dome/domehunter/logs/"
byobu send-keys Enter
byobu send-keys "echo tail -F -n 1000 server_log_yyyy_mm_dd.log"
byobu send-keys Enter
