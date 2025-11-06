import pytest
import numpy as np
from unittest.mock import patch, PropertyMock, MagicMock
import json
import time

from huntsman.pocs.camera.zwo import Camera
from huntsman.pocs.nats.streams import start_streams, delete_streams
from fake_asi_driver import FakeASIDriver


@pytest.fixture(autouse=True)
def reset_camera_driver():
    # Reset the singleton driver and camera list before each test
    Camera._driver = None
    Camera._cameras = []
    Camera._assigned_cameras = set()


@pytest.fixture
def camera_config():
    return {
        'name': 'ZWO ASI Camera',
        'port': '/dev/ttyZWO1',  # This will be ignored by the SDK camera
        'serial_number': '123456789',
    }


@pytest.fixture
def camera(camera_config):
    with patch('huntsman.pocs.camera.zwo.HuntsmanASIDriver', FakeASIDriver):
        camera = Camera(**camera_config)
        yield camera
        camera.__del__()


def test_camera_init(camera: Camera):
    assert camera.is_connected is True
    assert camera.name == 'ZWO ASI Camera'
    assert camera._serial_number == '123456789'


def test_camera_connect(camera: Camera):
    # The camera is already connected in __init__
    # We can call connect() again to check if it works
    camera.connect()
    assert camera.is_connected is True


def test_take_exposure(camera: Camera):
    with patch.object(Camera, 'is_ready', new_callable=PropertyMock(return_value=True)):
        readout_thread = camera.take_exposure(filename='test.fits')
        readout_thread.join()
        # Check that exposure status is idle after exposure
        assert camera._driver.get_exposure_status(camera._handle) == 'IDLE'


def test_readout(camera: Camera):
    # This is now more of an integration test
    with patch('huntsman.pocs.camera.zwo.fits_utils.write_fits') as mock_write_fits:
        camera._driver._exposure_status[camera._handle] = 'SUCCESS'
        camera._readout(filename='test.fits', width=1024, height=768, header={})
        mock_write_fits.assert_called_once()


def test_gain_setting(camera: Camera):
    # Test setting a valid gain
    camera.gain = 50
    assert camera.gain == 50

    # Test clipping high gain
    camera.gain = 150
    assert camera.gain == 100

    # Test clipping low gain
    camera.gain = -50
    assert camera.gain == 0


def test_image_type_setting(camera: Camera):
    # Test setting a valid image type
    camera.image_type = 'RAW8'
    assert camera.image_type == 'RAW8'

    # Test setting an invalid image type
    with pytest.raises(ValueError):
        camera.image_type = 'INVALID_TYPE'


def test_readout_failed(camera: Camera):
    camera._driver._exposure_status[camera._handle] = 'FAILED'
    with pytest.raises(Exception):
        camera._readout(filename='test.fits', width=1024, height=768, header={})


def test_divide_image_into_chunks(camera: Camera):
    image_data = np.zeros((16, 16))
    chunks = camera.divide_image_into_chunks(image_data, n_chunks_x=2, n_chunks_y=2)

    assert len(chunks) == 4
    assert chunks[0][0].shape == (8, 8)
    assert chunks[0][1] == (0, 0, 8, 8)
    assert chunks[0][2] == (0, 0)

    assert chunks[1][0].shape == (8, 8)
    assert chunks[1][1] == (8, 0, 16, 8)
    assert chunks[1][2] == (1, 0)

    assert chunks[2][0].shape == (8, 8)
    assert chunks[2][1] == (0, 8, 8, 16)
    assert chunks[2][2] == (0, 1)

    assert chunks[3][0].shape == (8, 8)
    assert chunks[3][1] == (8, 8, 16, 16)
    assert chunks[3][2] == (1, 1)


def test_create_chunk_headers(camera: Camera):
    base_headers = {'base_key': 'base_value'}
    chunk_coords = (0, 0, 8, 8)
    chunk_indices = (0, 0)
    headers = camera.create_chunk_headers(base_headers, chunk_coords, chunk_indices, 2, 2)

    assert headers['base_key'] == 'base_value'
    assert headers['chunk_x'] == '0'
    assert headers['chunk_y'] == '0'
    assert headers['width'] == '8'
    assert headers['height'] == '8'
    assert headers['total_chunks_x'] == '2'
    assert headers['total_chunks_y'] == '2'


def test_take_exposure_with_focus_offset(camera: Camera):
    camera.focuser = MagicMock()
    camera.focuser.position = 100
    camera.focuser.move_by.return_value = 110

    with patch.object(Camera, 'is_ready', new_callable=PropertyMock(return_value=True)):
        camera.take_exposure(focus_offset=10, filename='test.fits')

    camera.focuser.move_by.assert_called_once_with(10)
    assert camera._current_focus_offset == 10


@pytest.mark.asyncio
async def test_take_video_no_chunking(camera: Camera, nats_addr):
    camera.nats_server = nats_addr

    video_thread = camera.take_video(
        seconds=0.1,
        max_frames=2,
        frame_rate=10,
        duration=0.2,
        chunking_enabled=False
    )
    video_thread.join(timeout=2)

    assert not video_thread.is_alive()


def test_take_video_chunking(camera: Camera, nats_addr):
    camera.nats_server = nats_addr

    video_thread = camera.take_video(
        seconds=0.1,
        max_frames=1,
        frame_rate=10,
        duration=0.1,
        chunking_enabled=True
    )
    video_thread.join(timeout=2)

    assert not video_thread.is_alive()


def test_check_memory_usage(camera: Camera, tmp_path):
    status_file = tmp_path / "memory_status.json"
    with open(status_file, 'w') as f:
        json.dump({'memory_percent': 75.0, 'memory_total': 100.0}, f)

    camera.memory_status_file = str(status_file)
    camera.last_memory_check = 0  # force a check

    camera.check_memory_usage()
    assert camera.memory_usage == 75.0

    # Check that it doesn't check again if called within 2 seconds
    with open(status_file, 'w') as f:
        json.dump({'memory_percent': 80.0, 'memory_total': 100.0}, f)

    camera.check_memory_usage()
    assert camera.memory_usage == 75.0

    # Wait 2 seconds and check again
    time.sleep(2)
    camera.check_memory_usage()
    assert camera.memory_usage == 80.0
