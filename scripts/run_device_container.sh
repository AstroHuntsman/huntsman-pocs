#!/bin/bash

#This script should be all any device (other than the control computer)
#needs to run. The Pyro name server and config server should ideally be
#initialised beforehand (e.g. on the control computer).

#Download the latest docker image from docker hub
docker pull huntsmanarray/device_startup:latest

#Run the docker container
#Note that network=host to map container's ports to the hosts directly
#This is OK for the pis etc. but probably not for the control computer
#-it allows the container to run in interactive mode
#--cap-add SYS_ADMIN --device /dev/fuse is necessary for the SSHFS mount
docker run -it --network host --cap-add SYS_ADMIN --device /dev/fuse \
    huntsmanarray/device_startup:latest  
