#!/usr/bin/env bash
set -u

source ~/.bash_profile

# Sleep while the system initialises
sleep 20s

# Start the camera service and logs in a Byobu session
if byobu new-session -d -s huntsman -n camera-service; then
    byobu select-window -t camera-service
    byobu send-keys '/bin/bash'
    byobu send-keys Enter
    byobu send-keys '/var/huntsman/scripts/run-camera-service.sh'
    byobu send-keys Enter
    byobu new-window -n camera-logs
    byobu select-window -t camera-logs
    byobu send-keys 'sleep 30 && /bin/bash'
    byobu send-keys Enter
    byobu send-keys 'tail -F -n 10000 ${PANLOG}/huntsman.log'
    byobu send-keys Enter
fi
