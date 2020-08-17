#!/usr/bin/env python
"""
Script to start the config server. Make sure the Pyro name server is already
running.

Might be good to parse some args in the future, but doesn't seem necessary
now.
"""
from huntsman.pocs.utils.config import start_config_server

if __name__ == "__main__":

    # Start the config server
    start_config_server()
