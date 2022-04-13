import glob
import os
import shutil
import time
import pytest

import astropy.units as u
from astropy.io import fits

from panoptes.utils import error
from panoptes.utils.images import fits as fits_utils

from huntsman.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation
from huntsman.pocs.camera.utils import create_cameras_from_config


from huntsman.pocs.camera.group import CameraGroup, dispatch_parallel


@pytest.fixture(scope='function')
def cameras():
    return create_cameras_from_config()


@pytest.fixture(scope='function')
def patterns(cameras, images_dir):
    # It would be better to replace images_dir by images_dir.
    # However, problems with rmtree and SSHFS causes the autofocus code to hang.

    patterns = {}
    for cam_name, camera in cameras.items():
        patterns[cam_name] = {
            'base': os.path.join(images_dir, 'focus', camera.uid),
            'fine_plot': os.path.join(images_dir, 'focus', camera.uid, '*', 'fine-focus*.png'),
            'coarse_plot': os.path.join(images_dir, 'focus', camera.uid, '*', 'coarse-focus*.png')}
    return patterns


@pytest.fixture(scope='function')
def camera_group(cameras):
    return CameraGroup(cameras)


def test_cg_move_filterwheel(camera_group):

    camera_group.filterwheel_move_to(1, blocking=True)
    assert all([camera.filterwheel.position == 1 for camera in camera_group.cameras.values()])
    camera_group.filterwheel_move_to(2, blocking=True)
    assert all([camera.filterwheel.position == 2 for camera in camera_group.cameras.values()])


def test_cg_fw_move_to_dark_position(camera_group):

    assert all([camera.filterwheel._dark_position is not None
                for camera in camera_group.cameras.values()])

    # if any camera in the camera group is already at dark position, move all cameras to a non-dark position
    if any([camera.filterwheel.position == camera.filterwheel._dark_position
            for camera in camera_group.cameras.values()]):
        camera_group.filterwheel_move_to(2, blocking=True)

    assert all([camera.filterwheel.position != camera.filterwheel._dark_position
                for camera in camera_group.cameras.values()])

    camera_group.filterwheel_move_to(dark_position=True, blocking=True)

    assert all([camera.filterwheel.position == camera.filterwheel._dark_position
                for camera in camera_group.cameras.values()])


def test_cg_take_observation(camera_group):
    """
    Tests functionality of camera group take_observation()
    """
    field = Field('Test Observation', '20h00m43.7135s +22d42m39.0645s')
    observation = Observation(field, exptime=1.5 * u.second, filter_name='deux')
    observation.seq_time = '19991231T235959'
    camera_group.take_observation(observation, headers={}, blocking=True)
    time.sleep(7)

    # TODO: Should this go into the fields subdirectory?
    observation_patterns = []
    for _, camera in camera_group.cameras.items():
        pattern = os.path.join(observation.directory, camera.uid, observation.seq_time,
                               '*.fits*')
        observation_patterns.append(pattern)
    camera_group.logger.info(observation.directory)
    for pattern in observation_patterns:
        assert len(glob.glob(pattern)) == 1
        for _ in glob.glob(pattern):
            os.remove(_)


def test_cg_autofocus_with_plots(camera_group, patterns):

    try:
        camera_group.autofocus(make_plots=True, blocking=True)
        # loop over the camera patterns to check for plots
        for pattern in patterns.values():
            assert len(glob.glob(pattern['fine_plot'])) == 1
    finally:
        for pattern in patterns.values():
            shutil.rmtree(pattern['base'])


def test_cg_autofocus_coarse_with_plots(camera_group, patterns):

    try:
        camera_group.autofocus(coarse=True, make_plots=True, blocking=True)
        # loop over the camera patterns to check for plots
        for pattern in patterns.values():
            assert len(glob.glob(pattern['coarse_plot'])) == 1
    finally:
        for pattern in patterns.values():
            shutil.rmtree(pattern['base'])
