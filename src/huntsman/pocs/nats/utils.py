import asyncio
import time
import threading
import os
import numpy as np
from typing import Union, Dict, Any, Optional, Tuple, List
import json

from nats.js import JetStreamContext

from astropy.io import fits

_memory_usage_lock = asyncio.Lock()


async def get_memory_usage(memory_status_file: str) -> Tuple[float, float]:
    """Retrives the memory usage from the memory status file.
    If it does not exist, returns 0

    Args:
        memory_status_file: The filepath of the memory status file
    Return:
        tuple(float, float): A tuple containing the memory usage and the timestamp that the usage was recorded.
    Raises:
        FileNotFoundError: Raised if the specified file does not exist
    """
    if not os.path.exists(memory_status_file):
        raise FileNotFoundError(f"Error: memory status file does not exist: {memory_status_file}")
    async with _memory_usage_lock:
        with open(memory_status_file, "r") as f:
            data = json.load(f)
            return (data["memory_usage"], data["timestamp"])


async def update_memory_usage(memory_status_file: str, memory_usage: float, timestamp: Optional[float] = None) -> None:
    """Updates the memory usage file with a new value. Will create the file and
    add the new update if it does not already exist

    Args:
        memory_status_file: The pathname of the memory status file
        memory_usage: The value to update the memory status file with
        timestamp: The time the memory usage was recorded. If None, will use runtime timestamp.
    """
    if not timestamp:
        timestamp = time.time()
    try:
        _, existing_timestamp = await get_memory_usage(memory_status_file)
    except FileNotFoundError:
        os.makedirs(os.path.dirname(memory_status_file), exist_ok=True)
        existing_timestamp = 0
    except json.JSONDecodeError:  # File exists, but is empty, that's fine
        existing_timestamp = 0

    if existing_timestamp > timestamp:  # Don't update if we have stale data
        print(f"Warning: Attempted to write stale data to memory usage file. Will not update.")
        return

    async with _memory_usage_lock:
        with open(memory_status_file, "w") as f:
            status = {"timestamp": time.time(
            ), "memory_usage": memory_usage}
            json.dump(status, f)


def subject_from_stream_name(stream_name: str) -> str:
    """Given the name of a stream, generates the subjects it should publish to.
    Expects the stream format "camera_[type]_[name]"
    Where [type] is either 'memory' or 'disk'

    Args:
        stream_name: The name of the stream for which to get the associated subject
    Return:
        The name of the subject associated with this stream"""
    sub = stream_name.lower()
    if "memory" not in sub and "disk" not in sub:
        raise ValueError(f"Expected one of 'memory' or 'disk' in stream name, got: {sub}")
    sub = sub.replace("_", ".", 2)
    sub += ".>"  # greedy wildcard
    return sub


async def list_streams(js: JetStreamContext, mem_contains: str = "memory", disk_contains: str = "disk") -> Tuple[List[str], List[str]]:
    """List all streams matching our naming pattern.

    Args:
        js: The jetstream context to list the streams for
        mem_contains: The string that memory streams are expected to contain. Not case sensitive
        disk_pattern: The string that disk streams are expected to contain. Not case sensitive
    Return:
        memory_streams, disk_streams: The memory and disk streams found in the jetstream context

    """
    streams = await js.streams_info()
    memory_streams = []
    disk_streams = []

    for stream in streams:
        name = stream.config.name
        if mem_contains in name.lower():
            memory_streams.append(name)
        elif disk_contains in name.lower():
            disk_streams.append(name)

    # Sort streams by their index to match them correctly
    memory_streams.sort(key=lambda x: int(x.split("_")[-1]))
    disk_streams.sort(key=lambda x: int(x.split("_")[-1]))

    return memory_streams, disk_streams


def write_fits(data: np.ndarray, header: Union[Dict[str, Any], fits.Header], filename: str, exposure_event: Optional[threading.Event] = None, **kwargs):
    """Write FITS file to requested location.

    >>> from panoptes.utils.images import fits as fits_utils
    >>> data = np.random.normal(size=100)
    >>> header = { 'FILE': 'delete_me', 'TEST': True }
    >>> filename = str(getfixture('tmpdir').join('temp.fits'))
    >>> fits_utils.write_fits(data, header, filename)
    >>> assert os.path.exists(filename)

    >>> fits_utils.getval(filename, 'FILE')
    'delete_me'
    >>> data2 = fits_utils.getdata(filename)
    >>> assert np.array_equal(data, data2)

    Args:
        data (array_like): The data to be written.
        header (dict): Dictionary of items to be saved in header.
        filename (str): Path to filename for output.
        exposure_event (None|`threading.Event`, optional): A `threading.Event` that
            can be triggered when the image is written.
        kwargs (dict): Options that are passed to the `astropy.io.fits.PrimaryHDU.writeto`
            method.
    """
    if not isinstance(header, fits.Header):
        header = fits.Header(header)

    hdu = fits.PrimaryHDU(data, header=header)

    # Create directories if required.
    if os.path.dirname(filename):
        os.makedirs(os.path.dirname(filename), mode=0o775, exist_ok=True)

    try:
        hdu.writeto(filename, **kwargs)
    except OSError as err:
        print(f"Error writing image to {filename}: {err!r}")
    else:
        print(f"Image written to {filename}")
    finally:
        if exposure_event:
            exposure_event.set()
