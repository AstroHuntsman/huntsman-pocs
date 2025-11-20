import os
from unittest.mock import AsyncMock, MagicMock, patch
import threading
import json

import numpy as np
import pytest
from astropy.io import fits

from huntsman.pocs.nats.utils import write_fits, list_streams, get_memory_usage, update_memory_usage


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_memory_usage_reads_file(tmp_path):
    """Reads a valid JSON file and returns correct memory usage and timestamp."""
    file = tmp_path / "status.json"
    file.write_text(json.dumps({"memory_usage": 42.5, "timestamp": 1234.0}))
    usage, ts = await get_memory_usage(str(file))
    assert usage == 42.5
    assert ts == 1234.0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_memory_usage_missing_file():
    """Raises FileNotFoundError when the memory status file is missing."""
    with pytest.raises(FileNotFoundError):
        await get_memory_usage("/does/not/exist.json")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_memory_usage_creates_new_file(tmp_path):
    """Creates a new memory status file with usage and timestamp if none exists."""
    file = tmp_path / "status.json"
    await update_memory_usage(str(file), 67.2)
    data = json.loads(file.read_text())
    assert data["memory_usage"] == 67.2
    assert "timestamp" in data


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_memory_usage_overwrites_if_newer(tmp_path):
    """Overwrites file when provided timestamp is newer than existing one."""
    file = tmp_path / "status.json"
    file.write_text(json.dumps({"memory_usage": 11.0, "timestamp": 100.0}))
    with patch("huntsman.pocs.nats.utils.get_memory_usage", return_value=(11.0, 100.0)), \
            patch("time.time", return_value=200.0):
        await update_memory_usage(str(file), 99.9, timestamp=150.0)
    data = json.loads(file.read_text())
    assert data == {"timestamp": 200.0, "memory_usage": 99.9}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_memory_usage_ignores_stale_data(tmp_path, capsys):
    """Skips writing and prints a warning when attempting to write stale data."""
    file = tmp_path / "status.json"
    with patch("huntsman.pocs.nats.utils.get_memory_usage", return_value=(80.0, 500.0)):
        await update_memory_usage(str(file), 90.0, timestamp=100.0)
    assert "stale" in capsys.readouterr().out
    assert not file.exists()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_streams():
    """Test the list_streams function."""
    js = AsyncMock()

    # mock stream info objects
    stream_infos = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]
    stream_infos[0].config.name = "CAMERA_MEMORY_2"
    stream_infos[1].config.name = "CAMERA_DISK_1"
    stream_infos[2].config.name = "CAMERA_MEMORY_1"
    stream_infos[3].config.name = "OTHER_STREAM"
    stream_infos[4].config.name = "CAMERA_DISK_2"

    js.streams_info.return_value = stream_infos
    memory_streams, disk_streams = await list_streams(js)

    # Check the results
    assert memory_streams == ["CAMERA_MEMORY_1", "CAMERA_MEMORY_2"]
    assert disk_streams == ["CAMERA_DISK_1", "CAMERA_DISK_2"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_streams_no_streams():
    """Test list_streams with no matching streams."""
    js = AsyncMock()
    js.streams_info.return_value = []

    memory_streams, disk_streams = await list_streams(js)

    assert memory_streams == []
    assert disk_streams == []


@pytest.mark.unit
def test_write_fits(tmp_path):
    """Test the write_fits function."""
    filename = os.path.join(tmp_path, "test.fits")
    data = np.arange(100, dtype=np.uint16).reshape(10, 10)
    header = {"TESTKEY": "TESTVAL"}

    write_fits(data, header, filename)

    assert os.path.exists(filename)

    with fits.open(filename) as hdul:
        assert np.array_equal(hdul[0].data, data)
        assert hdul[0].header["TESTKEY"] == "TESTVAL"


@pytest.mark.unit
def test_write_fits_with_fits_header(tmp_path):
    """Test write_fits with an astropy fits.Header object."""
    filename = os.path.join(tmp_path, "test.fits")
    data = np.arange(100, dtype=np.uint16).reshape(10, 10)
    header = fits.Header()
    header["TESTKEY"] = "TESTVAL"

    write_fits(data, header, filename)

    assert os.path.exists(filename)

    with fits.open(filename) as hdul:
        assert np.array_equal(hdul[0].data, data)
        assert hdul[0].header["TESTKEY"] == "TESTVAL"


@pytest.mark.unit
def test_write_fits_creates_directory(tmp_path):
    """Test that write_fits creates the directory if it doesn't exist."""
    dir_path = os.path.join(tmp_path, "new_dir")
    filename = os.path.join(dir_path, "test.fits")
    data = np.arange(100, dtype=np.uint16).reshape(10, 10)
    header = {"TESTKEY": "TESTVAL"}

    assert not os.path.exists(dir_path)

    write_fits(data, header, filename)

    assert os.path.exists(filename)


@pytest.mark.unit
def test_write_fits_with_event(tmp_path):
    """Test that write_fits sets the event."""
    filename = os.path.join(tmp_path, "test.fits")
    data = np.arange(100, dtype=np.uint16).reshape(10, 10)
    header = {"TESTKEY": "TESTVAL"}
    event = threading.Event()

    write_fits(data, header, filename, exposure_event=event)

    assert event.is_set()
