import os
import pytest

from panoptes.pocs.core import POCS
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.mount import create_mount_simulator
from panoptes.pocs.dome import create_dome_simulator
# from panoptes.pocs.camera import create_camera_simulator

from huntsman.pocs.camera.utils import create_cameras_from_config
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

    return obs


@pytest.fixture(scope='function')
def pocs(observatory):
    pocs = POCS(observatory, run_once=True)
    yield pocs
    pocs.power_down()

# ==============================================================================


def test_prepare_cameras_dropping(observatory):
    """Test that unready camera is dropped."""
    cameras = observatory.cameras
    camera_names = cameras.keys()
    assert len(camera_names) > 1, "Expeted more than one camera."
    # Override class method
    cameras[camera_names[0]].is_ready = False
    # This should drop the unready camera
    observatory.prepare_cameras(max_attempts=1)
    assert len(observatory.cameras) == len(camera_names) - 1


def test_bad_observatory(config):
    huntsman_pocs = os.environ['HUNTSMAN_POCS']
    try:
        del os.environ['HUNTSMAN_POCS']
        with pytest.raises(SystemExit) as pytest_wrapped_e:
            Observatory()
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 'Must set HUNTSMAN_POCS variable'
    finally:
        os.environ['HUNTSMAN_POCS'] = huntsman_pocs


def test_take_flat_fields(pocs):
    """

    """
    os.environ['POCSTIME'] = '2020-04-29 08:10:00'
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    pocs.initialize()
    assert not pocs.observatory.past_midnight
    assert not pocs.is_dark(horizon='observe')
    assert not pocs.is_dark(horizon='focus')
    assert pocs.is_dark(horizon='flat')
    pocs.get_ready()
    pocs.observatory.take_flat_fields(alt=60, az=90, max_num_exposures=1,
                                      tolerance=0.5)
