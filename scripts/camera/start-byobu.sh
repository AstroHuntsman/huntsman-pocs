#!/usr/bin/env bash

# Sleep while the system initialises
sleep 30s

# Start the camera service and logs in a Byobu session
if byobu new-session -d -s huntsman -n camera-service; then
    byobu select-window -t camera-service
    byobu send-keys 'bash -l /var/huntsman/scripts/run-camera-service.sh'
    byobu send-keys Enter
    byobu select-window -t camera-logs
    byobu send-keys "bash -l -c 'tail -F -n 10000 ${PANDIR}/logs/huntsman.log'"
    byobu send-keys Enter
fi
