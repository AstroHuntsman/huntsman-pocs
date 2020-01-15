#!/bin/bash

#This script should be all any device (other than the control computer)
#needs to run. The Pyro name server and config server should ideally be
#initialised beforehand (e.g. on the control computer).

#Download the latest docker image from docker hub
docker pull huntsmanarray/device_startup:latest

#Run the docker container

#Note that network=host to map container's ports to the hosts directly
#This is OK for the pis etc. but probably not for the control computer.

#-it allows the container to run in interactive mode.

#--cap-add SYS_ADMIN --device /dev/fuse is necessary for the SSHFS mount.

#-v ~/.ssh:/root/.ssh allows the container to use the credentials of the host
#to setup ssh connections (i.e. the SSHFS). This is used for passwordless
#login to the control computer, ***which must already be setup between the host
#device and the control computer***.

docker run -it --network host --cap-add SYS_ADMIN --device /dev/fuse \
        -v ~/.ssh:/root/.ssh huntsmanarray/device_startup:latest  
