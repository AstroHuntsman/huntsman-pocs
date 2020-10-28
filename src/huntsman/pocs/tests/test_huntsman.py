import os
import threading
import time

import pytest
from astropy import units as u
from huntsman.pocs.camera.pyro.client import Camera as PyroCamera
from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory as Observatory
from panoptes.pocs import hardware
from panoptes.pocs.base import PanBase
from panoptes.pocs.core import POCS
from panoptes.pocs.dome import create_dome_from_config
from panoptes.pocs.mount import create_mount_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.utils import CountdownTimer
from panoptes.utils import error


def wait_for_running(sub, max_duration=90):
    """Given a message subscriber, wait for a RUNNING message."""
    timeout = CountdownTimer(max_duration)
    while not timeout.expired():
        topic, msg_obj = sub.receive_message()
        if msg_obj and 'RUNNING' == msg_obj.get('message'):
            return True
    return False


def wait_for_state(sub, state, max_duration=90):
    """Given a message subscriber, wait for the specified state."""
    timeout = CountdownTimer(max_duration)
    while not timeout.expired():
        topic, msg_obj = sub.receive_message()
        if topic == 'STATUS' and msg_obj and msg_obj.get('state') == state:
            return True
    return False


@pytest.fixture(scope='function')
def cameras(config_with_simulated_stuff):
    """Get the default cameras from the config."""
    return create_cameras_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def scheduler(config_with_simulated_stuff):
    site_details = create_location_from_config(config_with_simulated_stuff)
    return create_scheduler_from_config(config_with_simulated_stuff,
                                        observer=site_details['observer'])


@pytest.fixture(scope='function')
def dome(config_with_simulated_stuff):
    return create_dome_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def mount(config_with_simulated_stuff):
    return create_mount_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def observatory(config_with_simulated_stuff, db_type, cameras, scheduler, dome, mount):
    observatory = Observatory(
        config=config_with_simulated_stuff,
        cameras=cameras,
        scheduler=scheduler,
        dome=dome,
        mount=mount,
        db_type=db_type
    )
    return observatory


@pytest.fixture(scope='function')
def pocs(config_with_simulated_stuff, observatory):
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'

    pocs = POCS(observatory,
                run_once=True,
                config=config_with_simulated_stuff)

    yield pocs

    pocs.power_down()
