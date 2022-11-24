import os

import pytest
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.utils.time import CountdownTimer
from panoptes.pocs.core import POCS
from panoptes.pocs.dome import create_dome_from_config
from panoptes.pocs.mount import create_mount_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from huntsman.pocs.mount import create_mount_simulator
from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory as Observatory
from huntsman.pocs.utils.huntsman import create_huntsman_pocs


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
def cameras():
    """Get the default cameras from the config."""
    return create_cameras_from_config()


@pytest.fixture(scope='function')
def scheduler():
    site_details = create_location_from_config()
    return create_scheduler_from_config(observer=site_details['observer'])


@pytest.fixture(scope='function')
def dome():
    return create_dome_from_config()


@pytest.fixture(scope='function')
def mount():
    return create_mount_from_config()


@pytest.fixture(scope='function')
def observatory(db_type, cameras, scheduler, dome, mount):
    observatory = Observatory(
        cameras=cameras,
        scheduler=scheduler,
        dome=dome,
        mount=mount,
        db_type=db_type
    )
    return observatory


@pytest.fixture(scope='function')
def pocs(observatory):
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'

    pocs = POCS(observatory, run_once=True, simulators=['night', 'weather', 'power'])

    yield pocs

    pocs.power_down()


def test_create_huntsman_pocs():
    mount = create_mount_simulator()
    pocs = create_huntsman_pocs(mount=mount)
    assert pocs.is_initialized
