#!/bin/bash

#Download the latest docker image from docker hub
docker pull huntsmanarray/device_startup

#Run the docker container
#Note that network=host to map container's ports to the hosts directly
#This is OK for the pis etc. but probably not for the control computer
docker run huntsmanarray/device_startup:latest --network host
