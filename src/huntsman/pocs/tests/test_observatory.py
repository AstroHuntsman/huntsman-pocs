import os
import pytest

from panoptes.utils import error
from panoptes.utils.time import wait_for_events

from panoptes.pocs.core import POCS
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.mount import create_mount_simulator

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
        # TODO: Split into two tests
        if n_not_ready == n_cameras:
            with pytest.raises(error.PanError):
                observatory.prepare_cameras(max_attempts=1, sleep=1)
        else:
            observatory.prepare_cameras(max_attempts=1, sleep=1)
            assert len(observatory.cameras) == n_cameras - n_not_ready
    finally:
        cam_not_ready._exposure_event.clear()  # Clear the exposure event


def test_bad_observatory():
    """Test the observatory raises a RuntimeError if HUNTSMAN_POCS is not set."""
    huntsman_pocs = os.environ['HUNTSMAN_POCS']
    try:
        del os.environ['HUNTSMAN_POCS']
        with pytest.raises(RuntimeError):
            Observatory()
    finally:
        os.environ['HUNTSMAN_POCS'] = huntsman_pocs


def test_take_flat_fields(pocs):
    """

    """
    os.environ['POCSTIME'] = '2020-10-09 12:00:00'
    assert pocs.observatory.is_dark(horizon='flat') is True
    pocs.initialize()
    pocs.observatory.take_flat_fields(alt=60, az=90, required_exposures=1, tolerance=0.5)


def test_autofocus_cameras(observatory):
    """
    """
    observatory.last_focus_time = None
    assert observatory.coarse_focus_required
    events = observatory.autofocus_cameras()
    wait_for_events(list(events.values()), timeout=60)
    fname = observatory.coarse_focus_config['filter_name']
    assert all([c.filterwheel.current_filter == fname for c in observatory.cameras.values()])
    assert not observatory.coarse_focus_required
