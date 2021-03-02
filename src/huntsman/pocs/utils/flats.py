from contextlib import suppress

from astropy.stats import sigma_clipped_stats
from astropy import units as u
from panoptes.utils.images import fits as fits_utils
from panoptes.utils.images import crop_data

from panoptes.utils.time import current_time
from panoptes.utils.utils import get_quantity_value
from huntsman.pocs.utils.logger import logger as LOGGER


from astropy.coordinates import get_sun
from astropy.coordinates import AltAz


def get_flat_field_altaz(location):
    """ Return the alt/az opposite the Sun now at a given location.
    Args:
        location (astropy.coordinates.EarthLocation): The location.
    Returns:
        astropy.coordinates.AltAz: The alt/az opposite the Sun.
    """
    time_now = current_time()
    frame = AltAz(obstime=time_now, location=location)
    altaz_sun = get_sun(time_now).transform_to(frame)

    # We want the anti-solar direction
    alt = -1 * altaz_sun.alt  # Alt between -90 and 90 deg
    az = ((altaz_sun.az.to_value(u.deg) + 180) % 360) * u.deg  # Az between 0 and 360 deg

    return AltAz(alt=alt, az=az, obstime=time_now, location=location)


class FlatFieldSequence():
    """ Class to facilitate flat fields with automatic exposure time updates.
    """

    def __init__(self, target_counts, counts_tolerance, initial_exposure_time=1 * u.second,
                 min_exptime=0.0001 * u.second, max_exptime=60 * u.second, max_exposures=10,
                 required_exposures=5, cutout_size=300, bias=0, logger=None, ):
        """
        Args:
            target_counts (float): The target counts for each exposure.
            counts_tolerance (float): The tolerance on target_counts in counts for a
                good flat field exposure.
            initial_exposure_time (u.Quantity, optional): The initial exposure time, default 1s.
            min_exptime (Quantity, optional): The min exposure time.
            max_exptime (Quantity, optional): The max exposure time.
            max_exposures (int, optional): The maximum num exposures in the sequence.
            required_exposures (int, optional): The required number of good exposures in each
                camera.
            bias (int, optional): Biases to use for the exposure time calculations. If not
                provided, assumed 0.
            logger (logger, optional): The logger.
            cutout_size (int, optional): The cutout size in pixels. Useful for reducing memory
                usage and the impact of vignetting. Default 300.
        """
        if logger is None:
            logger = LOGGER
        self.logger = logger

        self._n_exposures = 0
        self._n_good_exposures = 0
        self._max_exposures = int(max_exposures)
        self._cutout_size = int(cutout_size)
        self._required_exposures = int(required_exposures)
        self._min_exptime = get_quantity_value(min_exptime, u.second) * u.second
        self._max_exptime = get_quantity_value(max_exptime, u.second) * u.second
        self._initial_exposure_time = get_quantity_value(initial_exposure_time) * u.second
        self._target_counts = get_quantity_value(target_counts, u.adu)
        self._counts_tolerance = get_quantity_value(counts_tolerance, u.adu)
        self._bias = int(bias)

        self._filenames = []
        self._exptimes = []
        self._average_counts = []
        self._times = []

    @property
    def status(self):
        """
        """
        is_finished = False
        if self._n_good_exposures >= self._required_exposures:
            is_finished = True
        elif self._n_exposures >= self._max_exposures:
            is_finished = True

        average_counts = None
        exptime = None
        with suppress(IndexError):
            average_counts = self._average_counts[-1]
            exptime = self._exptimes[-1]

        status = {"good_exposures": self._n_good_exposures,
                  "total_exposures": self._n_exposures,
                  "max_exposures": self._max_exposures,
                  "required_exposures": self._required_exposures,
                  "is_finished": is_finished,
                  "exptime": exptime,
                  "average_counts": average_counts}
        return status

    @property
    def is_finished(self):
        """ Return True if the exposure sequence is finished, else False.
        """
        return self.status["is_finished"]

    @property
    def min_exptime_reached(self):
        """ Check if the last exposure was at the minimum exposure time.
        Returns:
            bool: True if the min exposure time is reached, else False.
        """
        try:
            return self._exptimes[-1] <= self._min_exptime
        except IndexError:
            return False

    @property
    def max_exptime_reached(self):
        """ Check if the last exposure was at the maximum exposure time.
        Returns:
            bool: True if the max exposure time is reached, else False.
        """
        try:
            return self._exptimes[-1] >= self._max_exptime
        except IndexError:
            return False

    @property
    def is_too_faint(self):
        """ Check if the last exposure was too faint.
        Returns:
            bool: True if the last exposure was too faint, else False.
        """
        try:
            return self._average_counts[-1] + self._counts_tolerance < self._target_counts
        except IndexError:
            return False

    @property
    def is_too_bright(self):
        """ Check if the last exposure was too bright.
        Returns:
            bool: True if the last exposure was too bright, else False.
        """
        try:
            return self._average_counts[-1] - self._counts_tolerance > self._target_counts
        except IndexError:
            return False

    def update(self, filename, exptime, time_start):
        """ Update the sequence data with the previous iteration.
        Args:
            filename (str) The file to read the counts from.
            exptime (dict): The exposure times.
            time_start (datetime.datetime): The time that the exposures were started.
        """
        average_counts = self._get_average_counts(filename)

        self._average_counts.append(average_counts)
        self._times.append(time_start)
        self._exptimes.append(exptime)
        self._n_exposures += 1

        if self._validate_exposure(average_counts):
            self._n_good_exposures += 1

    def get_next_exptime(self, past_midnight):
        """ Calculate next exptime for flat fields, accounting for changes in sky brightness.
        Args:
            past_midnight (bool): True if past midnight (sky is getting brighter), False if not.
        Returns:
            astropy.Quantity: The next exposure time.
        """
        if self._n_exposures == 0:
            return self._initial_exposure_time

        elapsed_time = (current_time() - self._times[-1]).sec

        # Get data for specific camera
        previous_exptime = self._exptimes[-1]
        previous_counts = self._average_counts[-1]

        # Calculate next exptime
        exptime = previous_exptime * (self._target_counts / previous_counts)
        sky_factor = 2.0 ** (elapsed_time / 180.0)
        if past_midnight:
            exptime = exptime / sky_factor
        else:
            exptime = exptime * sky_factor
        exptime = exptime.to_value(u.second) * u.second

        # Make sure the exptime is within limits
        if exptime >= self._max_exptime:
            self.logger.warning(f"Truncating exptime at maximum value.")
            exptime = self._max_exptime

        elif exptime <= self._min_exptime:
            self.logger.warning(f"Truncating exptime at minimum value.")
            exptime = self._min_exptime

        return exptime

    def _get_average_counts(self, filename, min_counts=1):
        """ Read the data and calculate a clipped-mean count rate.
        Args:
            filename (str): The filename containing the data.
            min_counts (float): The minimum count rate returned by this function. Can cause
                problems if less than or equal to 0, so 1 (default) is a safe choice.
        Returns:
            float: The average counts.
        """
        data = self._load_fits_data(filename)

        # Calculate average counts per pixel
        average_counts, _, _ = sigma_clipped_stats(data - self._bias)
        if average_counts < min_counts:
            self.logger.warning('Clipping mean flat-field counts at minimum value: '
                                f'{average_counts}<{min_counts}.')
            average_counts = min_counts

        return average_counts

    def _validate_exposure(self, average_counts):
        """ Check if the previous exposures were either all too faint at the max exposure time, or
        all too bright at the minimum exposure time.
        Returns:
            bool: True if valid, False if not.
        """
        return abs(average_counts - self._target_counts) <= self._counts_tolerance

    def _load_fits_data(self, filename, dtype="float32"):
        """ Load FITS data, using a cutout if necessary.
        Args:
            filename (str): The FITS filename.
            dtype (str or Type): The data type for the returned array.
        Returns:
            np.array: The exposure data clipped to _cutout_size and given in dtype.
        """
        data = fits_utils.getdata(filename).astype(dtype)
        if self._cutout_size is not None:
            data = crop_data(data, box_size=self._cutout_size)
        return data
