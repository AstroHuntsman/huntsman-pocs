import os
import pytest

from astropy import units as u

from panoptes.utils.time import current_time

from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.mount import create_mount_simulator

from huntsman.pocs.core import HuntsmanPOCS
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


def test_prepare_cameras_dropping(observatory):
    """Test that unready camera is dropped."""
    cameras = observatory.cameras
    camera_names = list(cameras.keys())
    n_cameras = len(camera_names)
    assert n_cameras >= 1, "No cameras found in Observatory instance."
    # Ensure at least one camera is not ready
    cam_not_ready = cameras[camera_names[0]]
    cam_not_ready._exposure_event.set()
    assert not cameras[camera_names[0]].is_ready
    try:
        n_not_ready = 0
        for camera in cameras.values():
            if not camera.is_ready:
                n_not_ready += 1
        assert n_not_ready != 0
        observatory.prepare_cameras(max_attempts=1, sleep=1)
        assert len(observatory.cameras) == n_cameras - n_not_ready
    finally:
        cam_not_ready._exposure_event.clear()  # Clear the exposure event


def test_take_flat_fields(pocs):
    """ TODO: Improve this test!
    """
    os.environ['POCSTIME'] = '2020-10-09 08:45:00'
    assert pocs.is_safe(horizon="twilight_max")
    assert not pocs.observatory.is_past_midnight
    assert pocs.observatory.is_twilight
    pocs.initialize()
    pocs.observatory.take_flat_fields(alt=60, az=90, required_exposures=1, tolerance=0.5)


def test_autofocus_cameras_coarse(observatory):
    """
    """
    observatory.last_coarse_focus_time = None
    assert observatory.coarse_focus_required
    observatory.autofocus_cameras(coarse=True, blocking=True)

    fname = observatory._coarse_focus_filter
    assert all([c.filterwheel.current_filter == fname for c in observatory.cameras.values()])
    assert observatory.last_coarse_focus_time is not None
    assert not observatory.coarse_focus_required


def test_autofocus_cameras_fine(observatory):
    """
    """
    observatory.last_fine_focus_time = None
    assert observatory.fine_focus_required
    observatory.autofocus_cameras(coarse=False, blocking=True)

    assert observatory.last_fine_focus_time is not None
    assert not observatory.fine_focus_required


def test_focus_conditions(pocs):
    """
    """
    observatory = pocs.observatory

    temp_tol = 5 * u.Celsius
    focus_interval = 1 * u.hour

    observatory._fine_focus_temptol = temp_tol
    observatory._coarse_focus_temptol = temp_tol
    observatory._fine_focus_interval = focus_interval
    observatory._coarse_focus_interval = focus_interval

    # Test focus timedelta condition
    observatory.last_fine_focus_time = None
    observatory.last_coarse_focus_time = None
    assert observatory.fine_focus_required
    assert observatory.coarse_focus_required

    observatory.last_fine_focus_time = current_time()
    observatory.last_coarse_focus_time = current_time()
    assert not observatory.fine_focus_required
    assert not observatory.coarse_focus_required

    observatory.last_fine_focus_time = current_time() - 2 * focus_interval
    observatory.last_coarse_focus_time = current_time() - 2 * focus_interval
    assert observatory.fine_focus_required
    assert observatory.coarse_focus_required

    # Test focus temp condition
    observatory.last_fine_focus_time = current_time()
    observatory.last_coarse_focus_time = current_time()

    observatory.db.insert_current('weather', {'ambient_temp_C': 0})
    observatory.last_fine_focus_temp = 0 * u.Celsius
    observatory.last_coarse_focus_temp = 0 * u.Celsius

    assert not observatory.coarse_focus_required
    assert not observatory.fine_focus_required

    new_temp = temp_tol + 1 * u.Celsius
    observatory.db.insert_current('weather', {'ambient_temp_C': new_temp.to_value(u.Celsius)})
    assert observatory.coarse_focus_required
    assert observatory.fine_focus_required
