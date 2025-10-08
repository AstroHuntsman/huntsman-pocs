from typing import Tuple, List
from nats.js import JetStreamContext


async def list_streams(js: JetStreamContext, mem_pattern: str = "CAMERA_MEMERY_", disk_pattern: str = "CAMERA_DISK_") -> Tuple[List[str], List[str]]:
    """List all streams matching our naming pattern.

    Args:

    """
    streams = await js.streams_info()
    memory_streams = []
    disk_streams = []

    for stream in streams:
        name = stream.config.name
        if name.startswith(mem_pattern):
            memory_streams.append(name)
        elif name.startswith(disk_pattern):
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
