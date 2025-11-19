import pytest

from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.utils.location import create_location_from_config
from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.mount import create_mount_simulator
from huntsman.pocs.core import HuntsmanPOCS
from huntsman.pocs.observatory import HuntsmanObservatory as Observatory


@pytest.fixture(scope='function')
def cameras():
    return create_cameras_from_config()


@pytest.fixture(scope='function')
def mount():
    return create_mount_simulator()


@pytest.fixture
def observatory(mount, cameras, images_dir):
    """Return a valid Observatory instance with a specific config."""

    site_details = create_location_from_config()
    scheduler = create_scheduler_from_config(observer=site_details['observer'])

    obs = Observatory(scheduler=scheduler)
    obs.set_mount(mount)
    for cam_name, cam in cameras.items():
        obs.add_camera(cam_name, cam)

    # Add dummy safety function
    # Note this gets overridden when initialising HuntsmanPOCS
    # Add a dummy safety function
    def safety_func(*args, **kwargs):
        return True
    obs._is_safe = safety_func

    return obs


@pytest.fixture(scope='function')
def pocs(observatory):
    pocs = HuntsmanPOCS(observatory, run_once=True, simulators=["power", "weather"])
    yield pocs
    pocs.power_down()


def test_movie_mode_observation(pocs):
    """
    Test that the system can perform a movie mode observation.
    """
    # Start the POCS state machine
    pocs.run()

    # The state machine will run the observation and then exit.
    # We can add assertions here to check the results of the observation.
    # For example, we could check the logs for messages indicating that the
    # movie mode observation was successful.

    # For now, we will just assert that the observation was completed.
    assert pocs.observatory.current_observation.status['observed'] is True
