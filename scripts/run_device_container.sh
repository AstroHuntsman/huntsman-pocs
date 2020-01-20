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

#docker run -it --network host --cap-add SYS_ADMIN --device /dev/fuse \
#        -v ~/.ssh:/root/.ssh:ro huntsmanarray/device_startup:latest 
#^Unable to set permissions properly this way 

#Create a container 
CONTAINER_ID=$(docker create -it --network host --cap-add SYS_ADMIN \
        --device /dev/fuse huntsmanarray/device_startup:latest /bin/bash)

#Start the container
docker start $CONTAINER_ID

#Extract some environment variables from the container
CONTAINER_USER=$(docker exec $CONTAINER_ID echo $USER)
CONTAINER_HOME=$(docker exec $CONTAINER_ID echo $HOME)
CONTAINER_PANDIR=$(docker exec $CONTAINER_ID echo $PANDIR)

#Copy the ssh credentials from the host to the container
docker cp ~/.ssh $CONTAINER_ID:$CONTAINER_HOME/.ssh

#Allow ssh credentials to be accessed by huntsman user
docker exec -u root $CONTAINER_ID chown -R $CONTAINER_USER $CONTAINER_HOME/.ssh

#Run the device script
docker exec -it $CONTAINER_ID python $CONTAINER_PANDIR/huntsman-pocs/scripts/startup_device.py

#Finally, kill the container
docker exec -u root $CONTAINER_ID pkill bash
