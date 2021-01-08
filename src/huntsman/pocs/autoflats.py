import os
from contextlib import suppress
from collections import abc, defaultdict
from concurrent.futures import wait as wait_for_futures

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy import units as u
from astropy.io import fits
from astropy.nddata import Cutout2D

from panoptes.utils.time import current_time, wait_for_events
from panoptes.utils import get_quantity_value
from huntsman.pocs.utils.logger import logger as LOGGER


class AutoFlatFieldSequence():
    """ Class to facilitate flat fields with automatic exposure time updates.
    """

    def __init__(self, cameras, observation, initial_exposure_times=1*u.second,
                 timeout=10*u.second, min_exptime=0.0001*u.second, max_exptime=60*u.second,
                 max_attempts=10, required_exposures=5, target_scaling=0.16, scaling_tolerance=0.05,
                 logger=None, safety_func=None, biases=None, cutout_size=300):
        """
        Args:
            cameras (abc.Mapping): The camera name : Camera dictionary.
            observation (Observation): An observation object, e.g. a DitheredFlatObservation.
            initial_exposure_times (optional): The exposure times, can be a single value (or
                quantity) or an abc.Mapping with camera names as keys.
            timeout (Quantity, optional): The timeout to be used for exposures in addition to the
                exposure time.
            min_exptime (Quantity, optional): The min exposure time.
            max_exptime (Quantity, optional): The max exposure time.
            max_attempts (int, optional): The maximum num exposures before terminating the sequence.
            required_exposures (int, optional): The required number of good exposures in each
                camera.
            target_scaling (float, optional): The fractional well-fullness to aim for.
            scaling_tolerance (float, optional): The tolerance on target_scaling to count as a
                good flat field exposure.
            biases (optional, optional): Biases to use for the exposure time calculations. If not
                provided, a new set of biases will be acquired.
            safety_func (callable, optional): A callable function that returns the safety status
                as a bool.
            logger (logger, optional): The logger.
            cutout_size (int, optional): The cutout size in pixels. Useful for reducing memory
                usage and the impact of vignetting. Default 300.
        """
        if logger is None:
            logger = LOGGER
        self.logger = logger

        self.cameras = cameras
        self.observation = observation
        self._safety_func = safety_func
        self._timeout = get_quantity_value(timeout, u.second)
        self._cutout_size = int(cutout_size)

        self._seqidx = 0
        self._max_attempts = int(max_attempts)
        self._target_scaling = float(target_scaling)
        self._scaling_tolerance = float(scaling_tolerance)
        self._required_exposures = int(required_exposures)
        self._min_exptime = get_quantity_value(min_exptime, u.second) * u.second
        self._max_exptime = get_quantity_value(max_exptime, u.second) * u.second

        self._initial_exposure_times = self._parse_initial_exposure_times(initial_exposure_times)

        # Setup containers for sequence data
        self._biases = biases
        self._exptimes = defaultdict(list)
        self._average_counts = defaultdict(list)
        self._times = list()
        self._target_counts = dict()
        self._counts_tolerance = dict()

        self._calculate_target_counts()

    @property
    def is_finished(self):
        """ Return True if the exposure sequence is finished, else False.
        """
        if not self._is_safe:
            self.logger.warning("Finishing auto-flats because safety check has failed.")
            return True
        # Check if the required number of good exposures have been acquired
        n_good = np.array(list(self._count_good_exposures().values()))
        if (n_good >= self._required_exposures).all():
            self.logger.info("Finishing auto-flats because required exposures have been acquired.")
            return True
        # Check if we have reached the maximum number of exposures
        if self._seqidx >= self._max_attempts:
            self.logger.warning("Finishing auto-flats because max exposures has been reached.")
            return True
        # Check that some of the previous exposures are valid
        if not self._validate_previous_exposures():
            self.logger.warning("Finishing auto-flats because all exposures are invalid.")
            return True
        return False

    def take_next_exposures(self, past_midnight, headers=None):
        """ Take the next exposures in the sequence.
        Args:
            headers (list of dict, optional): Additional FITS headers to be written.
            past_midnight (bool): True if past midnight (sky is getting brighter), False if not.
        """
        self.logger.info(f"Taking auto-flat sequence {self._seqidx + 1}/"
                         f"{self._required_exposures}.")
        if not self._is_safe:
            return

        if self._biases is None:
            self._take_biases()

        # Take exposures with the next exposure times
        exptimes = self._get_next_exptimes(past_midnight)

        time_now = current_time()
        filenames = self._take_observation(exptimes, headers=headers)

        # Calculate average counts
        counts = self._get_average_counts(filenames)

        # Check which exposures were good and log exposure times
        self._update(counts, exptimes, time_now)

        # Take darks if we are finished
        if self.is_finished:
            self._take_darks(headers=headers)  # Implicit safety checking

    def _calculate_target_counts(self):
        """ Get the target counts and tolerance for each camera.
        """
        for cam_name, camera in self.cameras.items():
            try:
                bit_depth = camera.bit_depth.to_value(u.bit)
            except NotImplementedError:
                self.logger.debug(f'No bit_depth property for {cam_name}. Using 16.')
                bit_depth = 16

            self._target_counts[cam_name] = int(self._target_scaling * 2 ** bit_depth)
            self._counts_tolerance[cam_name] = int(self._scaling_tolerance * 2 ** bit_depth)

            self.logger.debug(f"Target counts for {cam_name}: {self._target_counts[cam_name]}"
                              f"±{self._counts_tolerance[cam_name]}.")

    def _update(self, average_counts, exptimes, time_now):
        """ Update the sequence data with the previous iteration.
        Args:
            average_counts (dict): The average counts.
            exptimes (dict): The exposure times.
            time_now (datetime.datetime): The time that the exposures were started.
        """
        for cam_name in self.cameras.keys():
            self._times.append(time_now)
            self._exptimes[cam_name].append(exptimes[cam_name])
            self._average_counts[cam_name].append(average_counts[cam_name])

        # Increment the sequence index
        self._seqidx += 1

    def _get_next_exptimes(self, past_midnight):
        """ Calculate the next exposure times for all the cameras.
        Returns:
            dict: The cam_name: exptime pairs.
        """
        if self._seqidx == 0:
            return self._initial_exposure_times
        elapsed_time = (current_time() - self._times[-1]).sec
        next_exptimes = {}
        for cam_name in self.cameras.keys():
            next_exptimes[cam_name] = self._get_next_exptime(cam_name, elapsed_time, past_midnight)
        return next_exptimes

    def _get_next_exptime(self, camera_name, elapsed_time, past_midnight):
        """Calculate the next exposure time for the flat fields, accounting for changes in sky
        brightness.
        Args:
            camera_name (str): The name of the camera.
            elapsed_time (astropy.Quantity): The time between the previous exposure and now.
            past_midnight (bool): True if past midnight (sky is getting brighter), False if not.
        Returns:
            astropy.Quantity: The next exposure time.
        """
        # Get data for specific camera
        previous_exptime = self._exptimes[camera_name][-1]
        target_counts = self._target_counts[camera_name]
        average_counts = self._average_counts[camera_name][-1]

        # Calculate next exptime
        exptime = previous_exptime * (target_counts / average_counts)
        sky_factor = 2.0 ** (elapsed_time / 180.0)
        if past_midnight:
            exptime = exptime / sky_factor
        else:
            exptime = exptime * sky_factor

        # Make sure the exptime is within limits
        exptime = exptime.to_value(u.second) * u.second
        if exptime >= self._max_exptime:
            self.logger.warning(f"Required exptime for {camera_name} is greater than the allowable"
                                " maximum.")
            exptime = self._max_exptime
        if exptime <= self._min_exptime:
            self.logger.warning(f"Required exptime for {camera_name} is less than the allowable"
                                " minimum.")
            exptime = self._min_exptime

        return exptime

    def _get_average_counts(self, filename_dict):
        """ Calculate the average counts for each camera.
        Args:
            filename_dict (dict): dict of cam_name: filename pairs.
        Returns:
            dict: cam_name: average_counts pairs.
        """
        counts = {}
        for cam_name, filename in filename_dict.items():
            counts[cam_name] = self._get_average_count(cam_name, filename)
            self.logger.debug(f"Average counts for {cam_name}: {counts[cam_name]:.1f}")
        return counts

    def _get_average_count(self, cam_name, filename, min_counts=1):
        """ Read the data and calculate a clipped-mean count rate.
        Args:
            filename (str): The filename containing the data.
            bias (float): The bias level to subtract from the image.
            min_counts (float): The minimum count rate returned by this function. Can cause
                problems if less than or equal to 0, so 1 (default) is a safe choice.
        Returns:
            float: The average counts.
        """
        try:
            data = self._load_fits_data(filename)
        except FileNotFoundError:
            data = self._load_fits_data(filename + ".fz")

        # Calculate average counts per pixel
        average_counts, _, _ = sigma_clipped_stats(data - self._biases[cam_name])
        if average_counts < min_counts:
            self.logger.warning('Clipping mean flat-field counts at minimum value: '
                                f'{average_counts}<{min_counts}.')
            average_counts = min_counts

        return average_counts

    def _take_biases(self, seconds=0):
        """ Take a bias exposure for each camera. Should only be run once per sequence.
        Args:
            seconds (optional, float): The exposure time in seconds, default 0.
            dtype (str): The data type for the exposure data, default float32.
        """
        self.logger.info("Taking biases for auto-flat fielding.")
        futures = []
        filenames = {}

        # Take the bias exposures
        for cam_name, camera in self.cameras.items():
            filename = self._get_bias_filename(camera)
            future = camera.take_exposure(filename=filename, seconds=seconds, dark=True)
            futures.append(future)
            filenames[cam_name] = filename

        # Wait for exposures to complete
        wait_for_futures(futures)

        # Read the biases
        self._biases = {}
        for cam_name, filename in filenames.items():
            self._biases[cam_name] = self._load_fits_data(filename)

    def _take_darks(self, **kwargs):
        """ Take the dark frames for each camera for each exposure time. This is potentially a
        long-running function, so we need to check safety frequently.
        Args:
            exptimes: dict of camera_name: list of exposure times.
        """
        self.logger.info("Taking darks for auto-flat fielding.")

        exptimes = self._exptimes.copy()  # Don't modify original exptimes
        # Exposure time lists may not be the same length for each camera
        while True:
            next_exptimes = {}
            for cam_name in exptimes.keys():
                with suppress(KeyError, IndexError):
                    next_exptimes[cam_name] = exptimes[cam_name].pop()

            # Break if we have finished all the cameras
            if not next_exptimes:
                break

            if self._is_safe():
                self._take_observation(next_exptimes, dark=True, **kwargs)
            else:
                self.logger.debug("Aborting flat-field darks because safety check failed.")
                return

    def _take_observation(self, exptimes, headers=None, dark=False, **kwargs):
        """
        Slew to flat field, take exposures and wait for them to complete.
        Returns a list of camera events for each camera.
        Args:
            exptimes (dict): Pairs of camera_name: list of exposure times.
            headers (dict): FITS headers to be written to file.
            dark (bool, optional): True if exposure is a dark exposure. Default False.
        Returns:
            dict: Dictionary of camera name : filename pairs.
        """
        events = []
        filenames = {}
        for cam_name, exptime in exptimes.items():
            cam = self.cameras[cam_name]

            # Create filename
            filename = self._get_exposure_filename(cam, dark=dark)

            # Take exposure and get event
            exptime = exptime.to_value(u.second)
            event = cam.take_observation(self.observation, headers=headers, filename=filename,
                                         exptime=exptime, dark=dark)
            events.append(event)
            filenames[cam_name] = filename

        # Block until exposures are complete
        self._wait_for_exposures(events, exptimes)
        return filenames

    def _wait_for_exposures(self, events, exptimes):
        """ Block until exposures have completed.
        Args:
            events: (list of threading.Event): The observation events.
            exptimes (dict): Dict of cam_name: exptime pairs.
        """
        timeout = max(exptimes.values()).to_value(u.second) + self._timeout

        # Block until done exposing on all cameras
        self.logger.debug(f"Waiting for flat-field exposures with timeout of {timeout}.")
        wait_for_events(events)

    def _get_exposure_filename(self, camera, dark=False):
        """ Get the exposure filename for a camera.
        Args:
            camera (Camera): A camera instance.
            dark (bool, optional): If True, is a dark exposure. Default False.
        """
        imtype = "dark" if dark else "flat"
        path = os.path.join(self.observation.directory, camera.uid, self.observation.seq_time)
        filename = os.path.join(
            path, f'{imtype}_{self.observation.current_exp_num:02d}.{camera.file_extension}')
        return filename

    def _get_bias_filename(self, camera):
        """ Get the bias filename for a camera.
        Args:
            camera (Camera): A camera instance.
        """
        path = os.path.join(self.observation.directory, camera.uid, self.observation.seq_time)
        filename = os.path.join(path, f'bias.{camera.file_extension}')
        return filename

    def _parse_initial_exposure_times(self, initial_exposure_times):
        """ Flexible parser to allow for dicts or a single value.
        Returns:
            dict: cam_name: exposure time pairs.
        """
        camera_names = list(self.cameras.keys())
        if isinstance(initial_exposure_times, abc.Mapping):
            return initial_exposure_times
        else:
            v = get_quantity_value(initial_exposure_times, u.second) * u.second
            return {c: v for c in camera_names}

    def _is_safe(self):
        """ Return True if safe to continue, else False.
        """
        if self._safety_func is None:
            self.logger.warning(f"Tried to check safety but {self} has no safety function.")
            return True
        is_safe = self._safety_func()
        if not is_safe:
            self.logger.warning(f"Safety check failed on {self}.")
        return is_safe

    def _count_good_exposures(self):
        """ Count the number of good exposures for each camera.
        Returns:
            dict: cam_name: number pairs.
        """
        number = {}
        for cam_name in self.cameras.keys():
            counts = np.array(self._average_counts[cam_name])
            target = self._target_counts[cam_name]

            n_good = abs(counts - target) < self._counts_tolerance[cam_name]
            number[cam_name] = n_good.sum()

            self.logger.debug(f"Current acceptable flat field exposures for {cam_name}: ",
                              f"{number[cam_name]}/{self._required_exposures}.")
        return number

    def _validate_previous_exposures(self):
        """ Check if the previous exposures were either all too faint at the max exposure time, or
        all too bright at the minimum exposure time.
        Returns:
            bool: True if valid, False if not.
        """
        if self._seqidx <= 1:
            return True

        # Check if all are too faint at the max exposure time, or if all are too bright at the min
        all_to_bright = True
        all_to_faint = True
        for cam_name, exptimes in self._exptimes.items():

            target_counts = self._target_counts[cam_name]
            counts_tolerance = self._counts_tolerance[cam_name]
            exptime = exptimes[-1]
            counts = self._average_counts[cam_name][-1]

            # Check exposure is too bright at min exposure time
            if exptime == self._min_exptime:
                all_to_bright &= counts > target_counts + counts_tolerance

            # Check if exposure is too faint at max exposure time
            if exptime == self._max_exptime:
                all_to_faint &= counts < target_counts - counts_tolerance

        if all_to_bright:
            self.logger.warning("All previous exposures were too bright at the minimum exptime.")
        if all_to_faint:
            self.logger.warning("All previous exposures were too faint at the maximum exptime.")

        return not (all_to_bright or all_to_faint)

    def _load_fits_data(self, filename, dtype="float32"):
        """ Load FITS data, using a cutout if necessary.
        Args:
            filename (str): The FITS filename.
            dtype (str or Type): The data type for the returned array.
        Returns:
            np.array: The exposure data.
        """
        data = fits.getdata(filename)
        if self._cutout_size is not None:
            x, y = data.shape[1]/2, data.shape[0]/2
            data = Cutout2D(data, (x, y), size=self._cutout_size).data
        return data.astype(dtype)
