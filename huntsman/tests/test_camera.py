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
import Pyro4.util

from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
from pocs.utils.images import fits as fits_utils
from pocs import error

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
        camera = PyroCamera(port=cam_name, uri=cam_uri)

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
        temperature = camera.temperature
    except NotImplementedError:
        pytest.skip("Camera {} doesn't implement temperature info".format(camera.name))
    else:
        assert temperature is not None


def test_is_cooled(camera):
    cooled_camera = camera.is_cooled_camera
    assert cooled_camera is not None


def test_set_target_temperature(camera):
    if camera.is_cooled_camera:
        camera._target_temperature = 10 * u.Celsius
        assert abs(camera._target_temperature - 10 * u.Celsius) < 0.5 * u.Celsius
    else:
        pytest.skip("Camera {} doesn't implement temperature control".format(camera.name))


def test_cooling_enabled(camera):
    cooling_enabled = camera.cooling_enabled
    if not camera.is_cooled_camera:
        assert not cooling_enabled


def test_enable_cooling(camera):
    if camera.is_cooled_camera:
        camera.cooling_enabled = True
        assert camera.cooling_enabled
    else:
        pytest.skip("Camera {} doesn't implement control of cooling status".format(camera.name))


def test_get_cooling_power(camera):
    if camera.is_cooled_camera:
        power = camera.cooling_power
        assert power is not None
    else:
        pytest.skip("Camera {} doesn't implement cooling power readout".format(camera.name))


def test_disable_cooling(camera):
    if camera.is_cooled_camera:
        camera.cooling_enabled = False
        assert not camera.cooling_enabled
    else:
        pytest.skip("Camera {} doesn't implement control of cooling status".format(camera.name))


def test_temperature_tolerance(camera):
    temp_tol = camera.temperature_tolerance
    camera.temperature_tolerance = temp_tol.value + 1
    assert camera.temperature_tolerance == temp_tol + 1 * u.Celsius
    camera.temperature_tolerance = temp_tol
    assert camera.temperature_tolerance == temp_tol


def test_is_temperature_stable(camera):
    if camera.is_cooled_camera:
        camera.target_temperature = camera.temperature
        camera.cooling_enabled = True
        time.sleep(1)
        assert camera.is_temperature_stable
        camera.cooling_enabled = False
        assert not camera.is_temperature_stable
        camera.cooling_enabled = True
    else:
        assert not camera.is_temperature_stable


def test_exposure(camera, tmpdir):
    """
    Tests basic take_exposure functionality
    """
    fits_path = str(tmpdir.join('test_exposure.fits'))
    if camera.is_cooled_camera and camera.cooling_enabled is False:
        camera.cooling_enabled = True
        time.sleep(5)  # Give camera time to cool
    assert camera.is_ready
    assert not camera.is_exposing
    # A one second normal exposure.
    exp_event = camera.take_exposure(filename=fits_path)
    assert camera.is_exposing
    assert not exp_event.is_set()
    assert not camera.is_ready
    # By default take_exposure is non-blocking, need to give it some time to complete.
    if isinstance(camera, FLICamera):
        time.sleep(10)
    else:
        time.sleep(5)
    # Output file should exist, Event should be set and camera should say it's not exposing.
    assert os.path.exists(fits_path)
    assert exp_event.is_set()
    assert not camera.is_exposing
    assert camera.is_ready
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
    with pytest.raises(error.PanError):
        camera.take_exposure(1 * u.second, filename=fits_path_2)
    if isinstance(camera, FLICamera):
        time.sleep(10)
    else:
        time.sleep(5)
    assert os.path.exists(fits_path_1)
    assert not os.path.exists(fits_path_2)
    assert fits_utils.getval(fits_path_1, 'EXPTIME') == 2.0


def test_exposure_scaling(camera, tmpdir):
    """Regression test for incorrect pixel value scaling.

    Checks for zero padding of LSBs instead of MSBs, as encountered
    with ZWO ASI cameras.
    """
    try:
        bit_depth = camera.bit_depth
    except NotImplementedError:
        pytest.skip("Camera does not have bit_depth attribute")
    else:
        fits_path = str(tmpdir.join('test_exposure_scaling.fits'))
        camera.take_exposure(filename=fits_path, dark=True, blocking=True)
        image_data, image_header = fits.getdata(fits_path, header=True)
        assert bit_depth == image_header['BITDEPTH'] * u.bit
        pad_bits = image_header['BITPIX'] - image_header['BITDEPTH']
        assert (image_data % 2**pad_bits).any()


def test_exposure_no_filename(camera):
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)


def test_exposure_not_connected(camera):
    camera._connected = False
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)
    camera._connected = True


def test_exposure_moving(camera, tmpdir):
    if not camera.filterwheel:
        pytest.skip("Camera does not have a filterwheel")
    fits_path_1 = str(tmpdir.join('test_not_moving.fits'))
    fits_path_2 = str(tmpdir.join('test_moving.fits'))
    camera.filterwheel.position = 1
    exp_event = camera.take_exposure(filename=fits_path_1)
    exp_event.wait()
    assert os.path.exists(fits_path_1)
    move_event = camera.filterwheel.move_to(2)
    with pytest.raises(error.PanError):
        camera.take_exposure(filename=fits_path_2)
    move_event.wait()
    assert not os.path.exists(fits_path_2)


def test_exposure_timeout(camera, tmpdir, caplog):
    """
    Tests response to an exposure timeout
    """
    fits_path = str(tmpdir.join('test_exposure_timeout.fits'))
    # Make timeout extremely short to force a timeout error
    original_timeout = camera._timeout
    camera._timeout = 0.01
    # This should result in a timeout error in the poll thread, but the exception won't
    # be seen in the main thread. Can check for logged error though.
    exposure_event = camera.take_exposure(seconds=0.1, filename=fits_path)
    # Wait for it all to be over.
    time.sleep(original_timeout)
    # Put the timeout back to the original setting.
    camera._timeout = original_timeout
    # Should be an ERROR message in the log from the exposure tiemout
    assert caplog.records[-1].levelname == "ERROR"
    # Should be no data file, camera should not be exposing, and exposure event should be set
    assert not os.path.exists(fits_path)
    assert not camera.is_exposing
    assert exposure_event is camera._exposure_event
    assert exposure_event.is_set()


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
    assert len(glob.glob(observation_pattern)) == 1


def test_autofocus_coarse(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    autofocus_event = camera.autofocus(coarse=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_fine(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    autofocus_event = camera.autofocus()
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_fine_blocking(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    autofocus_event = camera.autofocus(blocking=True)
    assert autofocus_event.is_set()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']


def test_autofocus_with_plots(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    autofocus_event = camera.autofocus(make_plots=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']
    assert len(glob.glob(patterns['fine_plot'])) == 1


def test_autofocus_coarse_with_plots(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    autofocus_event = camera.autofocus(coarse=True, make_plots=True)
    autofocus_event.wait()
    counter['value'] += 1
    assert len(glob.glob(patterns['final'])) == counter['value']
    assert len(glob.glob(patterns['coarse_plot'])) == 1


def test_autofocus_keep_files(camera, patterns, counter):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
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
