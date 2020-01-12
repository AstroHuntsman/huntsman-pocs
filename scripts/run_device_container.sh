#!/bin/bash

#This script should be all any device (other than the control computer)
#needs to run. The Pyro name server and config server should ideally be
#initialised beforehand (e.g. on the control computer).

#Download the latest docker image from docker hub
docker pull huntsmanarray/device_startup

#Run the docker container
#Note that network=host to map container's ports to the hosts directly
#This is OK for the pis etc. but probably not for the control computer
docker run huntsmanarray/device_startup:latest --network host
