import pytest
import numpy as np
import asyncio
from unittest.mock import MagicMock, patch

from astropy import units as u

from huntsman.pocs.camera.zwo import Camera


@pytest.fixture(autouse=True)
def reset_camera_driver():
    Camera._driver = None


@pytest.fixture
def camera_config():
    return {
        'name': 'ZWO ASI Camera',
        'port': '/dev/ttyZWO1',
        'serial_number': '123456789',
    }


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.version = '1.2.3'
    driver.get_devices.return_value = {'123456789': '/dev/ttyZWO1'}
    driver.get_camera_property.return_value = {
        'camera_ID': 0,
        'name': 'ZWO ASI1600MM Pro',
        'has_cooler': True,
        'is_color_camera': False,
        'bayer_pattern': None,
        'bit_depth': 12,
        'pixel_size': 3.8 * u.um,
        'supported_video_format': ['RAW8', 'RAW16'],
        'e_per_adu': 0.5,
    }
    driver.get_control_caps.return_value = {
        'GAIN': {
            'name': 'Gain',
            'is_writable': True,
            'max_value': 100,
            'min_value': 0,
            'is_auto_supported': True,
        },
        'EXPOSURE': {
            'name': 'Exposure',
            'is_writable': True,
            'max_value': 1000,
            'min_value': 0,
            'is_auto_supported': True,
        },
        'TEMPERATURE': {
            'name': 'Temperature',
            'is_writable': False,
        },
        'TARGET_TEMP': {
            'name': 'Target Temperature',
            'is_writable': True,
            'max_value': 30,
            'min_value': -20,
            'is_auto_supported': False,
        },
        'COOLER_POWER_PERC': {
            'name': 'Cooler Power',
            'is_writable': False,
        },
    }

    def get_control_value_side_effect(handle, control_type):
        if control_type == 'TEMPERATURE':
            return (10 * u.Celsius, True)
        elif control_type == 'COOLER_POWER_PERC':
            return (50 * u.percent, True)
        else:
            return (0, True)

    driver.get_control_value.side_effect = get_control_value_side_effect
    driver.get_video_data.return_value = np.zeros((10, 10), dtype='uint16')
    return driver


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
def test_camera_init(mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    camera = Camera(**camera_config)
    assert camera.is_connected is True
    assert camera.name == 'ZWO ASI Camera'
    assert camera._serial_number == '123456789'


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
def test_camera_connect(mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    camera = Camera(**camera_config)
    # The camera is already connected in __init__
    # We can call connect() again to check if it works
    camera.connect()

    assert camera.is_connected is True
    # The mock is called once in __init__ and once in connect()
    assert mock_driver.open_camera.call_count == 2
    assert mock_driver.init_camera.call_count == 2
    assert mock_driver.get_control_caps.call_count == 2


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
def test_take_exposure(mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    mock_driver.get_roi_format.return_value = {
        'width': 1024,
        'height': 768,
        'image_type': 'RAW16',
    }
    camera = Camera(**camera_config)

    readout_args = camera._start_exposure(seconds=1.0, filename='test.fits', dark=False, header={})
    assert readout_args[0] == 'test.fits'
    mock_driver.start_exposure.assert_called_once()


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
@patch('huntsman.pocs.camera.zwo.fits_utils.write_fits')
def test_readout(mock_write_fits, mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    mock_driver.get_exposure_status.return_value = 'SUCCESS'
    mock_driver.get_exposure_data.return_value = 'imagedata'

    camera = Camera(**camera_config)

    camera._readout(filename='test.fits', width=1024, height=768, header={})
    mock_write_fits.assert_called_once()


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
def test_take_video(mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    mock_driver.get_roi_format.return_value = {
        'width': 1024,
        'height': 768,
        'image_type': 'RAW16',
    }
    camera = Camera(**camera_config)

    with patch.object(camera, '_control_setter') as mock_control_setter:
        video_thread = camera.start_video(
            seconds=0.1,
            filename_root='test_video',
            max_frames=10,
            frame_rate=10,
            duration=1,
        )
        assert video_thread.is_alive() is True
        mock_driver.start_video_capture.assert_called_once()
        camera.stop_video()
        video_thread.join(timeout=2)
        assert video_thread.is_alive() is False
        mock_control_setter.assert_called_once_with('EXPOSURE', 0.1 * u.s)


@patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', new_callable=MagicMock)
@patch('huntsman.pocs.camera.zwo.asyncio.new_event_loop')
def test_publish_to_nats(mock_new_event_loop, mock_driver_class, camera_config, mock_driver):
    mock_driver_class.return_value = mock_driver
    camera = Camera(**camera_config)

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_new_event_loop.return_value = mock_loop

    camera._publish_frame_to_nats(frame_data=b'fakedata', headers={})
    mock_loop.run_until_complete.assert_called_once()

