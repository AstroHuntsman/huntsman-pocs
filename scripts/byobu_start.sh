#!/bin/bash

# Create new session.
SESSION_NAME=${1-Huntsman-Control}
byobu new-session -d -s "${SESSION_NAME}"

# To be able to actually see anything, you need to launch a terminal for the session
# normally this script will be run over ssh so normally we wont want to start a
# terminal window. If desired this behaviour can be enabled by uncommenting one
# of the lines below 
#gnome-terminal --window --maximize -- byobu attach -t "${SESSION_NAME}"
#xfce4-terminal --maximize -e "byobu attach -t '${SESSION_NAME}'

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
byobu select-window -t "${SESSION_NAME}":"main-control"

# setup the main-control window
# Select default pane. Probably an unnecessary line of code
byobu select-pane -t 0
# split window hoirzontaly
byobu split-window -h
# select pane 0
byobu select-pane -t 0
# split selected pane vertically
byobu split-window -v
# select the top pane
byobu select-pane -t 0
# split top pane vertically again
byobu split-window -v
# select the top pane
byobu select-pane -t 0
# run a command in selected pane, must end with 'Enter'
# in first pane we will setup the name server
byobu send-keys "echo $HUNTSMAN_POCS/scripts/pyro_name_server"
byobu send-keys Enter
# in second pane we will setup the config server
byobu select-pane -t 1
byobu send-keys "echo python $HUNTSMAN_POCS/scripts/start_config_server.py"
byobu send-keys Enter
# in the third pane we will set up the POCS ipython session
byobu select-pane -t 2
byobu send-keys "ipython"
byobu send-keys Enter
# pocs start up steps
pocsstart=("from panoptes.pocs.mount import create_mount_from_config"
            "from panoptes.pocs.scheduler import create_scheduler_from_config"
            "from huntsman.pocs.camera import create_cameras_from_config"
            "from huntsman.pocs.observatory import HuntsmanObservatory"
            "from panoptes.pocs.core import POCS"
            "from huntsman.pocs.utils import load_config"
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
    sleep .1
    byobu send-keys Enter
done
# in fourth pane we will set up the POCS logging window
byobu select-pane -t 3
byobu send-keys "echo grc tail -F -n 1000 $PANDIR/logs/ipython-all.log"
byobu send-keys Enter

# create shutter and weather window
byobu select-window -t "${SESSION_NAME}":"shutter-and-weather"
byobu split-window -h
byobu select-pane -t 0
byobu send-keys "ipython"
byobu send-keys Enter
# some times commands seem to get skipped over unless a pause is inserted
sleep .1
byobu send-keys "#from huntsman.pocs.dome.musca import HuntsmanDome"
byobu send-keys Enter
sleep .1
byobu send-keys "#from huntsman.pocs.utils import load_config"
byobu send-keys Enter
sleep .1
byobu send-keys "#config = load_config()"
byobu send-keys Enter
byobu send-keys "#dome = HuntsmanDome(config=config)"
byobu send-keys Enter
byobu send-keys "#dome.status()"
byobu send-keys Enter
byobu send-keys "#dome.open()"
byobu send-keys Enter
byobu select-pane -t 1
byobu split-window -v
byobu select-pane -t 1
byobu send-keys "echo $POCS/bin/peas_shell"
byobu send-keys Enter
byobu send-keys "echo load_weather"
byobu send-keys Enter
byobu send-keys "echo start"
byobu send-keys Enter
byobu send-keys "echo last_reading weather"
byobu send-keys Enter
byobu select-pane -t 2
byobu send-keys "echo grc tail -F $PANDIR/logs/peas_shell_all.log"
byobu send-keys Enter

# create camera server window
# TODO rewrite this so it can create n equal size panes for n cameras
byobu select-window -t "${SESSION_NAME}":"camera-servers"
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
ipsuffix=("141" "144" "145" "146" "149" "148")
for _pane in $(byobu list-panes -F '#P'); do
    # ssh into the pi
    byobu send-keys -t ${_pane} "echo ssh huntsman@$ipprefix${ipsuffix[${_pane}]}"
    byobu send-keys -t ${_pane} Enter
    # create a persistent byobu session on the pi
    # byobu send-keys -t ${_pane} "echo byobu"
    # byobu send-keys -t ${_pane} Enter
    # run camera server docker start up script
    byobu send-keys -t ${_pane} "echo $HUNTSMAN_POCS/scripts/run_device_container.sh"
    byobu send-keys -t ${_pane} Enter
done

# create camera server logs window
byobu select-window -t "${SESSION_NAME}":"camera-logs"
byobu split-window -h
byobu select-pane -t 0
byobu split-window -v
byobu split-window -v
byobu select-pane -t 3
byobu split-window -v
byobu split-window -v
byobu select-layout tiled
# now to display all the camera logs
for _pane in $(byobu list-panes -F '#P'); do
    # ssh into the pi
    byobu send-keys -t ${_pane} "echo ssh huntsman@$ipprefix${ipsuffix[${_pane}]}"
    byobu send-keys -t ${_pane} Enter
    # create a persistent byobu session on the pi
    byobu send-keys -t ${_pane} "echo byobu"
    byobu send-keys -t ${_pane} Enter
    # display camera server logs
    byobu send-keys -t ${_pane} "echo grc tail -F -n 1000 $PANDIR/logspyro_camera_server.py-all.log"
    byobu send-keys -t ${_pane} Enter
done

# create dome control window
byobu select-window -t "${SESSION_NAME}":"dome-control"
byobu split-window -h
# start up dome control server
byobu select-pane -t 0
byobu send-keys "echo python ~/huntsman-dome/domehunter/gRPC-server/huntsman_dome_server.py -r"
byobu send-keys Enter
# set up dome control log
byobu select-pane -t 1
byobu send-keys "echo grc tail -F -n 1000 ~/huntsman-dome/domehunter/logs/server_log_yyyy_mm_dd.log"
byobu send-keys Enter
