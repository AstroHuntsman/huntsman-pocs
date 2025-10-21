import os
import threading

import numpy as np
import pytest
from astropy.io import fits

from huntsman.pocs.nats.utils import write_fits


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
