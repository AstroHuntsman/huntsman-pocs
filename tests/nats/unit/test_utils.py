import os
from unittest.mock import AsyncMock, MagicMock
import threading

import numpy as np
import pytest
from astropy.io import fits

from huntsman.pocs.nats.utils import write_fits, list_streams


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
