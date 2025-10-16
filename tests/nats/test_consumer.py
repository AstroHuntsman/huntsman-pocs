import asyncio
import json
import os
import queue
from unittest.mock import AsyncMock, MagicMock, call

import numpy as np
import pytest
from astropy.io import fits

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig


@pytest.fixture
def consumer_config(tmp_path):
    """Fixture for ConsumerConfig."""
    return ConsumerConfig(
        consumer_output_dir=str(tmp_path),
        disable_file_writing=False,
        num_writer_threads=1
    )


@pytest.fixture
def mock_jetstream():
    """Fixture for a mocked JetStreamContext."""
    return AsyncMock()


@pytest.fixture
def consumer(consumer_config, mock_jetstream):
    """Fixture for a Consumer instance."""
    return Consumer(cfg=consumer_config, js=mock_jetstream, consumer_id="test_consumer")


def create_mock_msg(headers=None, data=None):
    """Helper function to create a mock NATS message."""
    msg = MagicMock()
    msg.headers = headers or {}
    msg.data = data or b""
    # Make the mock awaitable
    msg.ack = AsyncMock()
    return msg


def test_consumer_init(consumer, consumer_config, mock_jetstream):
    """Test Consumer initialization."""
    assert consumer.cfg == consumer_config
    assert consumer.js == mock_jetstream
    assert consumer.consumer_id == "test_consumer"
    assert consumer.running is True
    assert isinstance(consumer.file_write_queue, queue.Queue)


def test_is_chunked_data(consumer):
    """Test the is_chunked_data method."""
    assert consumer.is_chunked_data(create_mock_msg(headers={"chunk_x": "1"})) is True
    assert consumer.is_chunked_data(create_mock_msg(headers={"chunk_number": "1"})) is True
    assert consumer.is_chunked_data(create_mock_msg(headers={"not_a_chunk_header": "1"})) is False
    assert consumer.is_chunked_data(create_mock_msg(headers={})) is False


def test_create_fits_header_chunked(consumer):
    """Test create_fits_header_chunked method."""
    headers = {
        "width": "10",
        "height": "10",
        "frame_number": "1",
        "chunk_x": "0",
        "chunk_y": "0",
        "header": json.dumps({"EXPTIME": 1.0})
    }
    msg = create_mock_msg(headers=headers)
    fits_header = consumer.create_fits_header_chunked(msg)

    assert isinstance(fits_header, fits.Header)
    assert fits_header["NAXIS1"] == 10
    assert fits_header["NAXIS2"] == 10
    assert fits_header["FRAMENO"] == 1
    assert fits_header["CHUNX"] == 0
    assert fits_header["CHUNY"] == 0
    assert fits_header["EXPTIME"] == 1.0
    assert fits_header["CONSUMER"] == "test_consumer"


def test_create_fits_header_nochunk(consumer):
    """Test create_fits_header_nochunk method."""
    headers = {"header": json.dumps({"EXPTIME": 2.0})}
    msg = create_mock_msg(headers=headers)
    fits_header = consumer.create_fits_header_nochunk(msg)

    assert isinstance(fits_header, fits.Header)
    assert fits_header["EXPTIME"] == 2.0
    assert fits_header["CONSUMER"] == "test_consumer"


def test_create_frame_fname(consumer):
    """Test create_frame_fname method."""
    msg = create_mock_msg(headers={"frame_number": "42"})
    fname = consumer.create_frame_fname(msg, is_chunked=False, stream_type="memory")
    assert "frame_test_consumer_42" in fname
    assert "memory" in fname
    assert fname.endswith(".fits")

    msg_chunked = create_mock_msg(headers={"frame_number": "43", "chunk_x": "1", "chunk_y": "2"})
    fname_chunked = consumer.create_frame_fname(msg_chunked, is_chunked=True, stream_type="disk")
    assert "frame_test_consumer_43_chunk_1_2" in fname_chunked
    assert "disk" in fname_chunked
    assert fname_chunked.endswith(".fits")


def test_process_frame_data(consumer):
    """Test process_frame_data method."""
    # Test with valid data and dimensions
    data = np.arange(100, dtype=np.uint16).tobytes()
    msg = create_mock_msg(headers={"width": "10", "height": "10"}, data=data)
    frame_data = consumer.process_frame_data(msg)
    assert frame_data is not None
    assert frame_data.shape == (10, 10)
    assert np.array_equal(frame_data, np.arange(100, dtype=np.uint16).reshape(10, 10))

    # Test with empty data
    msg_empty = create_mock_msg(data=b"")
    assert consumer.process_frame_data(msg_empty) is None

    # Test with data that cannot be reshaped
    data_bad_shape = np.arange(101, dtype=np.uint16).tobytes()
    msg_bad_shape = create_mock_msg(headers={"width": "10", "height": "10"}, data=data_bad_shape)
    with pytest.raises(ValueError):
        consumer.process_frame_data(msg_bad_shape)


@pytest.mark.asyncio
async def test_get_stream_type_from_sub(consumer):
    """Test get_stream_type_from_sub method."""
    mock_sub = AsyncMock()
    mock_sub.consumer_info.return_value.stream = "camera_memory_test"
    stream_type = await consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type == "memory"

    mock_sub.consumer_info.return_value.stream = "camera_disk_test"
    stream_type = await consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type == "disk"

    mock_sub.consumer_info.return_value.stream = "unknown_stream"
    stream_type = await consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type is None


@pytest.mark.asyncio
async def test_process_stream(consumer, mocker):
    """Test the main process_stream loop."""
    # Mock the subscription and messages
    mock_sub = AsyncMock()
    data = np.ones((5, 5), dtype=np.uint16).tobytes()
    msg1 = create_mock_msg(headers={"width": "5", "height": "5"}, data=data)
    mock_sub.fetch.side_effect = [[msg1], []]
    mock_sub.consumer_info.return_value.stream = "camera_memory_test"

    # Mock dependencies
    mocker.patch.object(consumer, "process_frame_data", return_value=np.ones((5, 5)))
    mocker.patch.object(consumer, "create_fits_header_nochunk", return_value=fits.Header())
    mocker.patch.object(consumer, "create_frame_fname", return_value="test.fits")
    mock_put = mocker.patch.object(consumer.file_write_queue, "put")

    # Run the stream processing for a short time
    consumer.running = True
    try:
        await asyncio.wait_for(consumer.process_stream(mock_sub), timeout=1.0)
    except asyncio.TimeoutError:
        pass  # Expected timeout as it's an infinite loop

    # Assertions
    mock_sub.fetch.assert_called()
    msg1.ack.assert_called_once()
    mock_put.assert_called_once()
    assert consumer.stats.total_count == 1
    assert consumer.stats.memory_count == 1


def test_file_writer_thread(consumer, mocker):
    """Test the file writer thread."""
    # Mock write_fits
    mock_write_fits = mocker.patch("huntsman.pocs.nats.consumer.write_fits")

    # Start the writer thread
    consumer.start_writer_threads()

    # Put an item in the queue
    frame_data = np.zeros((2, 2))
    header = fits.Header()
    filepath = "dummy.fits"
    consumer.file_write_queue.put((frame_data, header, filepath))

    # Wait for the queue to be empty
    consumer.file_write_queue.join()

    # Check that write_fits was called correctly
    mock_write_fits.assert_called_once_with(frame_data, header, filepath)

    # Stop the thread
    consumer.running = False


@pytest.mark.asyncio
async def test_setup_consumers(consumer, mock_jetstream, mocker):
    """Test setting up memory and disk consumers."""
    # Test memory consumer setup
    await consumer.setup_memory_consumer()
    mock_jetstream.add_consumer.assert_called_with(
        "CAMERA_MEMORY_test_consumer",
        mocker.ANY  # Don't care about the exact config object
    )
    mock_jetstream.pull_subscribe.assert_called_with(
        "camera.memory.test_consumer.>",
        "memory_consumer_test_consumer",
        stream="CAMERA_MEMORY_test_consumer"
    )

    # Test disk consumer setup
    await consumer.setup_disk_consumer()
    mock_jetstream.add_consumer.assert_called_with(
        "CAMERA_DISK_test_consumer",
        mocker.ANY
    )
    mock_jetstream.pull_subscribe.assert_called_with(
        "camera.archive.test_consumer.>",
        "disk_consumer_test_consumer",
        stream="CAMERA_DISK_test_consumer"
    )
