# This is lightly edited copy of pocs/tests/test_camera.py from POCS. The intent is to
# apply all the same tests from there to the Camera class(es) in huntsman-pocs. This file
# should be udpated to track any changes to the tests in POCS.
import pytest

import os
import time
import glob
import sys

import astropy.units as u

import Pyro4

from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
from pocs.utils.images import fits as fits_utils

from huntsman.camera.pyro import Camera as PyroCamera

sys.excepthook = Pyro4.util.excepthook

params = [PyroCamera]
ids = ['pyro']


@pytest.fixture(scope='module')
def images_dir(tmpdir_factory):
    directory = tmpdir_factory.mktemp('images')
    return str(directory)


# Ugly hack to access id inside fixture
@pytest.fixture(scope='module', params=zip(params, ids), ids=ids)
def camera(request, images_dir, camera_server):
    if request.param[0] == PyroCamera:
        ns = Pyro4.locateNS()
        cameras = ns.list(metadata_all={'POCS', 'Camera'})
        cam_name, cam_uri = cameras.popitem()
        camera = PyroCamera(name=cam_name, uri=cam_uri)

    camera.config['directories']['images'] = images_dir
    return camera


@pytest.fixture(scope='module')
def counter(camera):
    return {'value': 0}


@pytest.fixture(scope='module')
def patterns(camera, images_dir):
    patterns = {'final': os.path.join(images_dir, 'focus', camera.uid, '*',
                                      ('*_final.' + camera.file_extension)),
                'fine_plot': os.path.join(images_dir, 'focus', camera.uid, '*',
                                          'fine_focus.png'),
                'coarse_plot': os.path.join(images_dir, 'focus', camera.uid, '*',
                                            'coarse_focus.png')}
    return patterns


def test_init(camera):
    """
    Test that camera got initialised as expected
    """
    assert camera.is_connected


def test_uid(camera):
    # Camera uid should be a string (or maybe an int?) of non-zero length. Assert True
    assert camera.uid


def test_get_temp(camera):
    try:
        temperature = camera.ccd_temp
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement temperature info".format(camera.name))
    else:
        assert temperature is not None


def test_set_set_point(camera):
    try:
        camera.ccd_set_point = 10 * u.Celsius
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement temperature control".format(camera.name))
    else:
        assert abs(camera.ccd_set_point - 10 * u.Celsius) < 0.5 * u.Celsius


def test_enable_cooling(camera):
    try:
        camera.ccd_cooling_enabled = True
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement control of cooling status".format(camera.name))
    else:
        assert camera.ccd_cooling_enabled is True


def test_get_cooling_power(camera):
    try:
        power = camera.ccd_cooling_power
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement cooling power readout".format(camera.name))
    else:
        assert power is not None


def test_disable_cooling(camera):
    try:
        camera.ccd_cooling_enabled = False
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement control of cooling status".format(camera.name))
    else:
        assert camera.ccd_cooling_enabled is False


def test_exposure(camera, tmpdir):
    """
    Tests basic take_exposure functionality
    """
    fits_path = str(tmpdir.join('test_exposure.fits'))
    # A one second normal exposure.
    camera.logger.debug(f'test_exposure fits_path={fits_path}')
    camera.take_exposure(filename=fits_path)
    # By default take_exposure is non-blocking, need to give it some time to complete.
    time.sleep(5)
    assert os.path.exists(fits_path)
    # If can retrieve some header data there's a good chance it's a valid FITS file
    header = fits_utils.getheader(fits_path)
    assert header['EXPTIME'] == 1.0
    assert header['IMAGETYP'] == 'Light Frame'


def test_exposure_blocking(camera, tmpdir):
    """
    Tests blocking take_exposure functionality. At least for now only SBIG cameras do this.
    """
    fits_path = str(tmpdir.join('test_exposure_blocking.fits'))
    # A one second exposure, command should block until complete so FITS
    # should exist immediately afterwards
    camera.take_exposure(filename=fits_path, blocking=True)
    assert os.path.exists(fits_path)
    # If can retrieve some header data there's a good chance it's a valid FITS file
    header = fits_utils.getheader(fits_path)
    assert header['EXPTIME'] == 1.0
    assert header['IMAGETYP'] == 'Light Frame'


def test_exposure_dark(camera, tmpdir):
    """
    Tests taking a dark. At least for now only SBIG cameras do this.
    """
    fits_path = str(tmpdir.join('test_exposure_dark.fits'))
    # A 1 second dark exposure
    camera.take_exposure(filename=fits_path, dark=True, blocking=True)
    assert os.path.exists(fits_path)
    # If can retrieve some header data there's a good chance it's a valid FITS file
    header = fits_utils.getheader(fits_path)
    assert header['EXPTIME'] == 1.0
    assert header['IMAGETYP'] == 'Dark Frame'


@pytest.mark.filterwarnings('ignore:Attempt to start exposure')
def test_exposure_collision(camera, tmpdir):
    """
    Tests attempting to take an exposure while one is already in progress.
    With the SBIG cameras this will generate warning but still should work. Don't do this though!
    """
    fits_path_1 = str(tmpdir.join('test_exposure_collision1.fits'))
    fits_path_2 = str(tmpdir.join('test_exposure_collision2.fits'))
    camera.take_exposure(2 * u.second, filename=fits_path_1)
    camera.take_exposure(1 * u.second, filename=fits_path_2)
    time.sleep(5)
    assert os.path.exists(fits_path_1)
    assert os.path.exists(fits_path_2)
    assert fits_utils.getval(fits_path_1, 'EXPTIME') == 2.0
    assert fits_utils.getval(fits_path_2, 'EXPTIME') == 1.0


def test_exposure_no_filename(camera):
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)


def test_exposure_not_connected(camera):
    camera._connected = False
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)
    camera._connected = True


def test_observation(camera, images_dir):
    """
    Tests functionality of take_observation()
    """
    field = Field('Test Observation', '20h00m43.7135s +22d42m39.0645s')
    observation = Observation(field, exptime=1.5 * u.second)
    observation.seq_time = '19991231T235959'
    camera.take_observation(observation, headers={})
    time.sleep(7)
    observation_pattern = os.path.join(images_dir, 'fields', 'TestObservation',
                                       camera.uid, observation.seq_time, '*.fits*')
    camera.logger.debug(f'Looking for observation pattern: {observation_pattern}')
    assert len(glob.glob(observation_pattern)) == 1


def test_autofocus_coarse(camera, patterns, counter):
    autofocus_event = camera.autofocus(coarse=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_fine(camera, patterns, counter):
    autofocus_event = camera.autofocus()
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_fine_blocking(camera, patterns, counter):
    autofocus_event = camera.autofocus(blocking=True)
    assert autofocus_event.is_set()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_with_plots(camera, patterns, counter):
    autofocus_event = camera.autofocus(make_plots=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']
    assert len(glob.glob(patterns['fine_plot'])) == 1


def test_autofocus_coarse_with_plots(camera, patterns, counter):
    autofocus_event = camera.autofocus(coarse=True, make_plots=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']
    assert len(glob.glob(patterns['fine_plot'])) == 1
    assert len(glob.glob(patterns['coarse_plot'])) == 1


def test_autofocus_keep_files(camera, patterns, counter):
    autofocus_event = camera.autofocus(keep_files=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_no_size(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    thumbnail_size = camera.focuser.autofocus_size
    camera.focuser.autofocus_size = None
    with pytest.raises(ValueError):
        camera.autofocus()
    camera.focuser.autofocus_size = thumbnail_size
    assert camera.focuser.position == initial_focus


def test_autofocus_no_seconds(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    seconds = camera.focuser.autofocus_seconds
    camera.focuser.autofocus_seconds = None
    with pytest.raises(ValueError):
        camera.autofocus()
    camera.focuser.autofocus_seconds = seconds
    assert camera.focuser.position == initial_focus


def test_autofocus_no_step(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    autofocus_step = camera.focuser.autofocus_step
    camera.focuser.autofocus_step = None
    with pytest.raises(ValueError):
        camera.autofocus()
    camera.focuser.autofocus_step = autofocus_step
    assert camera.focuser.position == initial_focus


def test_autofocus_no_range(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    autofocus_range = camera.focuser.autofocus_range
    camera.focuser.autofocus_range = None
    with pytest.raises(ValueError):
        camera.autofocus()
    camera.focuser.autofocus_range = autofocus_range
    assert camera.focuser.position == initial_focus


def test_autofocus_camera_disconnected(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    camera._connected = False
    with pytest.raises(AssertionError):
        camera.autofocus()
    camera._connected = True
    assert camera.focuser.position == initial_focus


def test_autofocus_focuser_disconnected(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    camera.focuser._connected = False
    with pytest.raises(AssertionError):
        camera.autofocus()
    camera.focuser._connected = True
    assert camera.focuser.position == initial_focus


def test_autofocus_no_focuser(camera):
    try:
        initial_focus = camera.focuser.position
    except AttributeError:
        pytest.skip("Camera does not have an exposed focuser attribute")
    initial_focus = camera.focuser.position
    focuser = camera.focuser
    camera.focuser = None
    with pytest.raises(AttributeError):
        camera.autofocus()
    camera.focuser = focuser
    assert camera.focuser.position == initial_focus
