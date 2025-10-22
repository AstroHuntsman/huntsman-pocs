import asyncio
import json
import queue
from unittest.mock import AsyncMock, MagicMock
from tempfile import TemporaryDirectory

import numpy as np
import pytest
from astropy.io import fits

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig, ConsumerStats


@pytest.fixture
def consumer_config(tmp_path):
    """Fixture for ConsumerConfig."""
    return ConsumerConfig(
        consumer_output_dir=str(tmp_path),
        disable_file_writing=False,
        num_writer_threads=1
    )


@pytest.fixture
def mock_js():
    """Mock JetStream context."""
    js = MagicMock()
    js.add_consumer = AsyncMock()
    js.pull_subscribe = AsyncMock()
    return js


@pytest.fixture
def empty_consumer(consumer_config, mock_js):
    """Fixture for a Consumer instance. It's a real consumer but with a mocked jetstream component"""
    return Consumer(cfg=consumer_config, js=mock_js, consumer_id="test_consumer")


def create_mock_msg(headers=None, data=None):
    """Helper function to create a mock NATS message."""
    msg = MagicMock()
    msg.headers = headers or {}
    msg.data = data or b""
    # Make the mock awaitable
    msg.ack = AsyncMock()
    return msg


def test_consumer_stats(capsys):
    """Test the ConsumerStats class."""
    stats = ConsumerStats()
    stats.increment("memory")
    assert stats.memory_count == 1
    assert stats.total_count == 1

    stats.increment("disk")
    assert stats.disk_count == 1
    assert stats.total_count == 2

    stats.increment("invalid")
    assert stats.total_count == 3
    captured = capsys.readouterr()
    assert "Found invalid stream type: invalid" in captured.out


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consumer_init(empty_consumer: Consumer, consumer_config):
    """Test Consumer initialization."""
    assert empty_consumer.cfg == consumer_config
    assert empty_consumer.consumer_id == "test_consumer"
    assert empty_consumer.running is True
    assert isinstance(empty_consumer.file_write_queue, queue.Queue)


@pytest.mark.unit
def test_consumer_init_no_file_writing():
    """Test Consumer initialization with file writing disabled."""
    with TemporaryDirectory() as tmp_dir:
        config = ConsumerConfig(
            consumer_output_dir=str(tmp_dir),
            disable_file_writing=True
        )
        consumer = Consumer(cfg=config, js=mock_js, consumer_id="test_consumer_ini_no_file_writing")
        assert consumer.cfg.disable_file_writing is True
        # Check that directories are not created
        assert consumer.memory_dir is None
        assert consumer.disk_dir is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consumer_shutdown(empty_consumer: Consumer):
    """Test the shutdown method."""
    assert empty_consumer.running is True
    await empty_consumer.shutdown()
    assert empty_consumer.running is False
    # Test double shutdown
    await empty_consumer.shutdown()
    assert empty_consumer.running is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_is_chunked_data(empty_consumer: Consumer):
    """Test the is_chunked_data method."""
    assert empty_consumer.is_chunked_data(create_mock_msg(headers={"chunk_x": "1"})) is True
    assert empty_consumer.is_chunked_data(create_mock_msg(headers={"chunk_number": "1"})) is True
    assert empty_consumer.is_chunked_data(create_mock_msg(
        headers={"not_a_chunk_header": "1"})) is False
    assert empty_consumer.is_chunked_data(create_mock_msg(headers={})) is False


@pytest.mark.unit
def test_create_fits_header_chunked(empty_consumer: Consumer):
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
    fits_header = empty_consumer.create_fits_header_chunked(msg)

    assert isinstance(fits_header, fits.Header)
    assert fits_header["NAXIS1"] == 10
    assert fits_header["NAXIS2"] == 10
    assert fits_header["FRAMENO"] == 1
    assert fits_header["CHUNX"] == 0
    assert fits_header["CHUNY"] == 0
    assert fits_header["EXPTIME"] == 1.0
    assert fits_header["CONSUMER"] == "test_consumer"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_fits_header_chunked_missing_headers(empty_consumer: Consumer):
    """Test create_fits_header_chunked with missing headers."""
    msg = create_mock_msg(headers={})
    fits_header = empty_consumer.create_fits_header_chunked(msg)
    assert isinstance(fits_header, fits.Header)
    assert "DATE-OBS" in fits_header
    assert "NAXIS1" not in fits_header  # No dimensions provided


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_fits_header_nochunk(empty_consumer: Consumer):
    """Test create_fits_header_nochunk method."""
    headers = {"header": json.dumps({"EXPTIME": 2.0})}
    msg = create_mock_msg(headers=headers)
    fits_header = empty_consumer.create_fits_header_nochunk(msg)

    assert isinstance(fits_header, fits.Header)
    assert fits_header["EXPTIME"] == 2.0
    assert fits_header["CONSUMER"] == "test_consumer"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_fits_header_nochunk_invalid_json(empty_consumer: Consumer, capsys):
    """Test create_fits_header_nochunk with invalid JSON."""
    headers = {"header": "not json"}
    msg = create_mock_msg(headers=headers)
    fits_header = empty_consumer.create_fits_header_nochunk(msg)
    assert isinstance(fits_header, fits.Header)
    assert "DATE-OBS" in fits_header
    captured = capsys.readouterr()
    assert "Error parsing header" in captured.out


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_frame_fname(empty_consumer: Consumer):
    """Test create_frame_fname method."""
    msg = create_mock_msg(headers={"frame_number": "42"})
    fname = empty_consumer.create_frame_fname(msg, is_chunked=False, stream_type="memory")
    assert "frame_test_consumer_42" in fname
    assert "memory" in fname
    assert fname.endswith(".fits")

    msg_chunked = create_mock_msg(headers={"frame_number": "43", "chunk_x": "1", "chunk_y": "2"})
    fname_chunked = empty_consumer.create_frame_fname(
        msg_chunked, is_chunked=True, stream_type="disk")
    assert "frame_test_consumer_43_chunk_1_2" in fname_chunked
    assert "disk" in fname_chunked
    assert fname_chunked.endswith(".fits")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_frame_fname_chunk_number(empty_consumer: Consumer):
    """Test create_frame_fname with chunk_number."""
    msg = create_mock_msg(headers={"frame_number": "44", "chunk_number": "3"})
    fname = empty_consumer.create_frame_fname(msg, is_chunked=True, stream_type="memory")
    assert "frame_test_consumer_44_chunk_3" in fname


@pytest.mark.asyncio
@pytest.mark.unit
async def test_process_frame_data(empty_consumer: Consumer):
    """Test process_frame_data method."""
    # Test with valid data and dimensions
    data = np.arange(100, dtype=np.uint16).tobytes()
    msg = create_mock_msg(headers={"width": "10", "height": "10"}, data=data)
    frame_data = empty_consumer.process_frame_data(msg)
    assert frame_data is not None
    assert frame_data.shape == (10, 10)
    assert np.array_equal(frame_data, np.arange(100, dtype=np.uint16).reshape(10, 10))

    # Test with empty data
    msg_empty = create_mock_msg(data=b"")
    assert empty_consumer.process_frame_data(msg_empty) is None

    # Test with data that cannot be reshaped
    data_bad_shape = np.arange(101, dtype=np.uint16).tobytes()
    msg_bad_shape = create_mock_msg(headers={"width": "10", "height": "10"}, data=data_bad_shape)
    with pytest.raises(ValueError):
        empty_consumer.process_frame_data(msg_bad_shape)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_process_frame_data_square_reshape(empty_consumer: Consumer):
    """Test process_frame_data with automatic square reshaping."""
    data = np.arange(100, dtype=np.uint16).tobytes()
    msg = create_mock_msg(data=data)  # No width/height headers
    frame_data = empty_consumer.process_frame_data(msg)
    assert frame_data.shape == (10, 10)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_stream_type_from_sub(empty_consumer: Consumer):
    """Test get_stream_type_from_sub method."""
    mock_sub = AsyncMock()
    mock_sub.consumer_info.return_value.stream = "camera_memory_test"
    stream_type = await empty_consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type == "memory"

    mock_sub.consumer_info.return_value.stream = "camera_disk_test"
    stream_type = await empty_consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type == "disk"

    mock_sub.consumer_info.return_value.stream = "unknown_stream"
    stream_type = await empty_consumer.get_stream_type_from_sub(mock_sub)
    assert stream_type is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_process_stream(empty_consumer: Consumer, mocker):
    """Test the main process_stream loop."""
    # Mock the subscription and messages
    mock_sub = AsyncMock()
    data = np.ones((5, 5), dtype=np.uint16).tobytes()
    msg1 = create_mock_msg(headers={"width": "5", "height": "5"}, data=data)
    mock_sub.fetch.side_effect = [[msg1], []]
    mock_sub.consumer_info.return_value.stream = "camera_memory_test"

    # Mock dependencies
    mocker.patch.object(empty_consumer, "process_frame_data", return_value=np.ones((5, 5)))
    mocker.patch.object(empty_consumer, "create_fits_header_nochunk", return_value=fits.Header())
    mocker.patch.object(empty_consumer, "create_frame_fname", return_value="test.fits")
    mock_put = mocker.patch.object(empty_consumer.file_write_queue, "put")

    # Run the stream processing for a short time
    empty_consumer.running = True
    try:
        await asyncio.wait_for(empty_consumer.process_stream(mock_sub), timeout=1.0)
    except asyncio.TimeoutError:
        pass  # Expected timeout as it's an infinite loop

    # Assertions
    mock_sub.fetch.assert_called()
    msg1.ack.assert_called_once()
    mock_put.assert_called_once()
    assert empty_consumer.stats.total_count == 1
    assert empty_consumer.stats.memory_count == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_file_writer_thread(empty_consumer: Consumer, mocker):
    """Test the file writer thread."""
    mock_write_fits = mocker.patch("huntsman.pocs.nats.consumer.write_fits")
    empty_consumer.start_writer_threads()

    # Put an item in the queue
    frame_data = np.zeros((2, 2))
    header = fits.Header()
    filepath = "dummy.fits"
    empty_consumer.file_write_queue.put((frame_data, header, filepath))
    empty_consumer.file_write_queue.join()  # Wait for the queue to be empty

    mock_write_fits.assert_called_once_with(frame_data, header, filepath)
    empty_consumer.running = False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_file_writer_thread_exception(empty_consumer: Consumer, mocker, capsys):
    """Test the file writer thread with an exception during file writing."""
    mocker.patch("huntsman.pocs.nats.consumer.write_fits", side_effect=Exception("Disk full"))
    empty_consumer.start_writer_threads()

    # Put an item in the queue
    empty_consumer.file_write_queue.put((np.zeros((2, 2)), fits.Header(), "dummy.fits"))
    empty_consumer.file_write_queue.join()  # Wait for the queue to be empty

    captured = capsys.readouterr()
    assert "Error writing file: Disk full" in captured.out
    empty_consumer.running = False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_report_stats(empty_consumer: Consumer, mocker):
    """Test the report_stats method."""

    empty_consumer.stats.total_count = 10
    empty_consumer.stats.memory_count = 6
    empty_consumer.stats.disk_count = 4
    empty_consumer.file_write_queue.put(1)  # Add item to queue

    # Mock time to control FPS calculation
    mock_time = mocker.patch("time.time")
    mock_time.side_effect = lambda: 100.0 + (mock_time.call_count - 1) * 5.0

    # Capture print output
    mock_print = mocker.patch("builtins.print")

    # Run report_stats for a short time
    empty_consumer.running = True
    task = asyncio.create_task(empty_consumer.report_stats())
    await asyncio.sleep(0.1)
    empty_consumer.running = False
    await task

    # Assertions
    mock_print.assert_called_with(
        "Consumer test_consumer: Processed 10 frames (6 memory, 4 disk), 2.00 FPS, Queue size: 1"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_setup_consumers(empty_consumer: Consumer, mocker):
    """Test setting up memory and disk consumers."""
    # Test memory consumer setup
    await empty_consumer.setup_memory_consumer()
    empty_consumer.js.add_consumer.assert_called_with(
        "CAMERA_MEMORY_test_consumer",
        mocker.ANY  # Don't care about the exact config object
    )
    empty_consumer.js.pull_subscribe.assert_called_with(
        "camera.memory.test_consumer.>",
        "memory_consumer_test_consumer",
        stream="CAMERA_MEMORY_test_consumer"
    )

    # Test disk consumer setup
    await empty_consumer.setup_disk_consumer()
    empty_consumer.js.add_consumer.assert_called_with(
        "CAMERA_DISK_test_consumer",
        mocker.ANY
    )
    empty_consumer.js.pull_subscribe.assert_called_with(
        "camera.archive.test_consumer.>",
        "disk_consumer_test_consumer",
        stream="CAMERA_DISK_test_consumer"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_setup_memory_consumer_exception(empty_consumer: Consumer, capsys):
    """Test setup_memory_consumer with an exception."""
    empty_consumer.js.add_consumer.side_effect = Exception("NATS error")
    await empty_consumer.setup_memory_consumer()
    captured = capsys.readouterr()
    assert "ERROR: Memory consumer setup note: NATS error" in captured.out


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_consumer(empty_consumer: Consumer, mocker):
    """Test the main run_consumer method."""
    # Mock methods that are called by run_consumer
    mock_start_writers = mocker.patch.object(empty_consumer, "start_writer_threads")
    mock_setup_mem = mocker.patch.object(
        empty_consumer, "setup_memory_consumer", new_callable=AsyncMock)
    mock_setup_disk = mocker.patch.object(
        empty_consumer, "setup_disk_consumer", new_callable=AsyncMock)
    mock_process = mocker.patch.object(empty_consumer, "process_stream", new_callable=AsyncMock)
    mock_report = mocker.patch.object(empty_consumer, "report_stats", new_callable=AsyncMock)
    mock_join = mocker.patch.object(empty_consumer.file_write_queue, "join")

    # Make process_stream and report_stats raise an exception to break the loop
    mock_process.side_effect = [Exception("stop loop"), Exception("stop loop")]

    await empty_consumer.run_consumer()

    # Assertions
    mock_start_writers.assert_called_once()
    mock_setup_mem.assert_called_once()
    mock_setup_disk.assert_called_once()
    assert mock_process.call_count == 2
    mock_report.assert_called_once()
    mock_join.assert_called_once()
    assert empty_consumer.running is False
