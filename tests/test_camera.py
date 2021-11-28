"""This is lightly edited copy of pocs/tests/test_camera.py from panoptes.pocs.

The intent is to apply all the same tests from there to the Camera class(es) in huntsman-pocs.
This file should be updated to track any changes to the tests in POCS.
"""
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
from huntsman.pocs.utils.pyro.nameserver import get_running_nameserver
from huntsman.pocs.camera.pyro.client import Camera


@pytest.fixture(scope='function')
def patterns(camera, images_dir):
    # It would be better to replace images_dir by images_dir.
    # However, problems with rmtree and SSHFS causes the autofocus code to hang.

    patterns = {'base': os.path.join(images_dir, 'focus', camera.uid),
                'fine_plot': os.path.join(images_dir, 'focus', camera.uid, '*',
                                          'fine-focus*.png'),
                'coarse_plot': os.path.join(images_dir, 'focus', camera.uid, '*',
                                            'coarse-focus*.png')}
    return patterns


@pytest.fixture(scope='function')
def camera(camera_service_name):
    nameserver = get_running_nameserver()
    camera_client = Camera(uri=nameserver.lookup(camera_service_name))

    # Seems to be a bug somewhere with missing camera._exposure_error attribute
    # TODO: Remove
    camera_client._exposure_error = None

    return camera_client


def test_tune_exptime(camera):
    """ Test exposure time tuning. """
    initial_exptime = 1 * u.second

    target = 1
    exptime = camera.tune_exposure_time(target, initial_exptime, max_steps=1)
    assert exptime > initial_exptime
    exptime = camera.tune_exposure_time(target, initial_exptime, max_steps=1,
                                        max_exptime=initial_exptime)
    assert initial_exptime == exptime

    target = 0
    exptime = camera.tune_exposure_time(target, initial_exptime, max_steps=1)
    assert exptime < initial_exptime
    exptime = camera.tune_exposure_time(target, initial_exptime, max_steps=1,
                                        min_exptime=initial_exptime)
    assert initial_exptime == exptime


def test_camera_detection(camera):
    assert camera


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
    assert cooled_camera in {True, False}


def test_set_target_temperature(camera):
    if camera.is_cooled_camera:
        camera.target_temperature = 10 * u.Celsius
        assert abs(camera.target_temperature - 10 * u.Celsius) < 0.5 * u.Celsius
    else:
        pytest.skip(f"Camera {camera.name} doesn't implement temperature control")


def test_cooling_enabled(camera):
    cooling_enabled = camera.cooling_enabled
    if not camera.is_cooled_camera:
        assert not cooling_enabled


def test_enable_cooling(camera):
    if camera.is_cooled_camera:
        camera.cooling_enabled = True
        assert camera.cooling_enabled
    else:
        pytest.skip(f"Camera {camera.name} doesn't implement control of cooling status")


def test_get_cooling_power(camera):
    if camera.is_cooled_camera:
        power = camera.cooling_power
        assert power is not None
    else:
        pytest.skip(f"Camera {camera.name} doesn't implement cooling power readout")


def test_disable_cooling(camera):
    if camera.is_cooled_camera:
        camera.cooling_enabled = False
        assert not camera.cooling_enabled
    else:
        pytest.skip(f"Camera {camera.name} doesn't implement control of cooling status")


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


def test_move_filterwheel(camera):
    if not camera.filterwheel:
        pytest.skip("Camera does not have a filterwheel.")
    camera.filterwheel.move_to(1, blocking=True)
    assert camera.filterwheel.position == 1
    camera.filterwheel.move_to(2, blocking=True)
    assert camera.filterwheel.position == 2


def test_fw_move_to_dark_position(camera):
    if not camera.filterwheel:
        pytest.skip("Camera does not have a filterwheel.")

    assert camera.filterwheel._dark_position is not None

    camera.filterwheel.move_to(1, blocking=True)
    if camera.filterwheel.position == camera.filterwheel._dark_position:
        camera.filterwheel.move_to(2, blocking=True)

    camera.filterwheel.move_to_dark_position(blocking=True)
    assert camera.filterwheel.position == camera.filterwheel._dark_position


def test_exposure(camera, tmpdir):
    """ Tests basic take_exposure functionality """
    fits_path = str(tmpdir.join('test_exposure.fits'))
    if camera.is_cooled_camera and camera.cooling_enabled is False:
        camera.cooling_enabled = True
        time.sleep(5)  # Give camera time to cool
    assert camera.is_ready
    assert not camera.is_exposing
    assert not camera._proxy.get("is_exposing")
    assert not os.path.exists(fits_path)
    # Move filterwheel before exposure.
    camera.filterwheel.move_to(1, blocking=True)

    assert os.path.isfile(os.path.join(os.environ['POCS'], 'tests', 'data', 'unsolved.fits'))

    # A one second normal exposure
    assert os.path.exists(os.path.dirname(fits_path))
    readout_future = camera.take_exposure(seconds=1, filename=fits_path)
    assert readout_future.running()
    assert camera.is_exposing
    assert not camera.is_ready

    # By default take_exposure is non-blocking, need to give it some time to complete.
    readout_future.result(30)  # 30 second timeout

    # Output file should exist, Event should be set and camera should say it's not exposing.
    assert os.path.exists(fits_path)
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
    fits_path = os.path.join(str(tmpdir), 'test_exposure_blocking.fits')
    # A one second exposure, command should block until complete so FITS
    # should exist immediately afterwards
    assert camera.is_ready
    assert not camera.is_exposing
    assert not camera._proxy.get("is_exposing")
    camera.take_exposure(filename=fits_path, blocking=True)
    assert not camera._proxy.event_is_set("camera")
    assert camera.is_ready
    assert not camera.is_exposing
    assert os.path.isfile(fits_path)
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
    time.sleep(10)
    assert not camera.is_exposing
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
        assert (image_data % 2 ** pad_bits).any()


def test_exposure_no_filename(camera):
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)


def test_exposure_not_connected(camera):
    camera._connected = False
    with pytest.raises(AssertionError):
        camera.take_exposure(1.0)
    camera._connected = True


@pytest.mark.skip("Does not work. Get working after camera code refactor.")
def test_exposure_moving(camera, tmpdir):
    if not camera.filterwheel:
        pytest.skip("Camera does not have a filterwheel")
    fits_path_1 = str(tmpdir.join('test_not_moving.fits'))
    fits_path_2 = str(tmpdir.join('test_moving.fits'))
    camera.filterwheel.position = 1
    camera.take_exposure(filename=fits_path_1, blocking=True)
    assert os.path.exists(fits_path_1)
    move_event = camera.filterwheel.move_to(2)
    with pytest.raises(error.PanError):
        camera.take_exposure(filename=fits_path_2)
    move_event.wait()
    assert not os.path.exists(fits_path_2)


@pytest.mark.skip("Get working after camera refactor")
def test_service_exposure_timeout(camera, tmpdir, caplog):
    """
    Tests response to an exposure timeout
    """
    fits_path = str(tmpdir.join('test_exposure_timeout.fits'))
    # Make timeout extremely short to force a timeout error
    original_timeout = camera._proxy.get("_timeout")
    camera._proxy.set("_timeout", 0.01)
    # Need to fudge readout_time, too.
    original_readout_time = camera._proxy.get("_readout_time")
    camera._proxy.set("_readout_time", 0.01)
    # This should result in a timeout error in the poll thread, but the exception won't
    # be seen in the main thread. Can check for logged error though.
    exposure_event = camera.take_exposure(seconds=0.01, filename=fits_path)
    # Wait timeout to happen.
    time.sleep(0.5)
    # Put values back to originals
    camera._proxy.set("_timeout", original_timeout)
    camera._proxy.set("_readout_time", original_readout_time)
    # Should be an ERROR message in the log from the exposure timeout
    # assert caplog.records[-1].levelname == "ERROR"
    # Should be no data file, camera should not be exposing, and exposure event should be set
    assert not os.path.exists(fits_path)
    assert not camera.is_exposing
    assert exposure_event is camera._exposure_event
    assert exposure_event.is_set()
    # The camera didn't actually fail, so should wait for it to really finish.
    time.sleep(5)


def test_client_exposure_timeout(camera, tmpdir):
    fits_path = str(tmpdir.join('test_client_exposure_timeout.fits'))
    with pytest.raises(error.Timeout):
        camera.take_exposure(seconds=1, filename=fits_path, timeout=0.1, blocking=True)
    time.sleep(1.5)  # Let the exposure actually finish
    assert camera.is_ready


def test_observation(camera):
    """
    Tests functionality of take_observation()
    """
    field = Field('Test Observation', '20h00m43.7135s +22d42m39.0645s')
    observation = Observation(field, exptime=1.5 * u.second, filter_name='deux')
    observation.seq_time = '19991231T235959'
    camera.take_observation(observation, headers={})
    time.sleep(7)
    # TODO: Should this go into the fields subdirectory?
    observation_pattern = os.path.join(observation.directory, camera.uid, observation.seq_time,
                                       '*.fits*')
    camera.logger.info(observation.directory)
    assert len(glob.glob(observation_pattern)) == 1
    for _ in glob.glob(observation_pattern):
        os.remove(_)


def test_observation_nofilter(camera, images_dir):
    """
    Tests functionality of take_observation()
    """
    field = Field('Test Observation', '20h00m43.7135s +22d42m39.0645s')
    observation = Observation(field, exptime=1.5 * u.second, filter_name=None)
    observation.seq_time = '19991231T235959'
    camera.take_observation(observation, headers={})
    time.sleep(7)
    # TODO: Should this go into the fields subdirectory?
    observation_pattern = os.path.join(observation.directory, camera.uid, observation.seq_time,
                                       '*.fits*')
    assert len(glob.glob(observation_pattern)) == 1
    for _ in glob.glob(observation_pattern):
        os.remove(_)


def test_autofocus_with_plots(camera, patterns):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    try:
        camera.autofocus(make_plots=True, blocking=True)
        assert len(glob.glob(patterns['fine_plot'])) == 1
    finally:
        shutil.rmtree(patterns['base'])


def test_autofocus_coarse_with_plots(camera, patterns):
    if not camera.focuser:
        pytest.skip("Camera does not have a focuser")
    try:
        camera.autofocus(coarse=True, make_plots=True, blocking=True)
        assert len(glob.glob(patterns['coarse_plot'])) == 1
    finally:
        shutil.rmtree(patterns['base'])


@pytest.mark.skip("Defocusing logic has not been built into testing cameras!")
def test_observation_defocused(camera):
    """
    """
    if not camera.has_focuser:
        pytest.skip("Camera does not have a focuser.")

    field = Field('Test Observation', '20h00m43.7135s +22d42m39.0645s')
    observation = Observation(field, exptime=1.5 * u.second, filter_name='deux', defocused=True)
    observation.seq_time = '19991231T235959'

    camera._defocus_offset = 5
    focus_value_initial = camera.focuser.position
    camera.take_observation(observation, blocking=True)

    focus_value_final = camera.focuser.position
    assert focus_value_final == focus_value_initial + camera._defocus_offset

    observation2 = Observation(field, exptime=1.5 * u.second, filter_name='deux', defocused=False)
    observation2.seq_time = '19991231T235959'
    camera.take_observation(observation2, blocking=True)
    focus_value_final = camera.focuser.position
    assert focus_value_final == focus_value_initial
