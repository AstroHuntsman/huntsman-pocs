import threading
import os
import numpy as np
from typing import Union, Dict, Any, Optional

from astropy.io import fits


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
