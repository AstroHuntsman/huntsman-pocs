#!/usr/bin/env python
"""
Script to run a Pyro camera server. This should be run on the camera control computer for a
distributed camera. The configuration for the camera is read from the pyro_camera.yaml/
pyro_camera_local.yaml config file. The camera servers should be started after the name server,
but before POCS.
"""
import argparse
from huntsman.pocs.utils.pyro.camera_server import run_camera_server

if __name__ == "__main__":
    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument("--ignore_local",
                        help="Ignore pyro_camera_local.yaml config file",
                        action="store_true")
    args = parser.parse_args()

    # Run the camera server
    run_camera_server(ignore_local=args.ignore_local)
