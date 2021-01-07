import os
from contextlib import suppress
from collections import abc, defaultdict

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy import units as u
from astropy.io import fits

from panoptes.utils.time import current_time, wait_for_events
from panoptes.utils import get_quantity_value
from huntsman.pocs.utils.logger import logger as LOGGER


class AutoFlatFieldSequence():

    def __init__(self, cameras, observation, initial_exposure_times=1*u.second,
                 timeout=10*u.second, logger=None, safety_func=None, min_exptime=0.0001*u.second,
                 max_exptime=60*u.second, max_attempts=10):
        """
        """
        if logger is None:
            logger = LOGGER
        self.logger = logger

        self._seqidx = 0
        self._max_attempts = int(max_attempts)
        self._observation = observation
        self._min_exptime = get_quantity_value(min_exptime, u.second) * u.second
        self._max_exptime = get_quantity_value(max_exptime, u.second) * u.second
        self._timeout = get_quantity_value(timeout, u.second)
        self._safety_func = safety_func

        self._initial_exposure_times = self._parse_initial_exposure_times(initial_exposure_times)

        # Setup containers for sequence data
        self._biases = dict()
        self._exptimes = defaultdict(list)
        self._times = defaultdict(list)
        self._average_counts = defaultdict(list)
        self._target_counts = dict()
        self._counts_tolerance = dict()

        self._calculate_target_counts()

    @property
    def is_finished(self):
        """ Return True if the exposure sequence is finished, else False.
        """
        if not self._is_safe:
            return True
        # Check if the required number of good exposures have been acquired
        if (self._count_good_exposures() >= self._required_exposures).all():
            return True
        # Check if we have reached the maximum number of exposures
        return self._seqidx >= self._max_attempts

    def take_next_exposures(self, headers=None):
        """ Take the next exposures in the sequence.
        Args:
            headers (list of dict, optional): Additional FITS headers to be written.
        """
        if not self._is_safe:
            return

        if self._seqidx == 0:
            self._take_biases()

        # Take exposures with the next exposure times
        exptimes = self._get_next_exptimes()

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
            self._counts_tolerance[cam_name] = int(self._tolerance * 2 ** bit_depth)

            self.logger.debug(f'Target counts for {cam_name}: '
                              f'{self.target_counts[cam_name]}±{self.counts_tolerance[cam_name]}.')

    def _update(self, average_counts, exptimes, time_now):
        """ Update the sequence data with the previous iteration.
        Args:
            average_counts (dict): The average counts.
            exptimes (dict): The exposure times.
            time_now (datetime.datetime): The time that the exposures were started.
        """
        for cam_name in self.cameras.keys():
            self._exptimes[cam_name].append(exptimes)
            self._times[cam_name].append(time_now)
            self._average_counts[cam_name].append(average_counts)

        # Increment the sequence index
        self._seqidx += 1

    def _get_next_exptimes(self):
        """ Calculate the next exposure times for all the cameras.
        Returns:
            dict: The cam_name: exptime pairs.
        """
        if self._seqidx == 0:
            return self._initial_exposure_times
        elapsed_time = current_time() - self._times[-1]
        next_exptimes = {}
        for cam_name in self.cameras.keys():
            next_exptimes[cam_name] = self._get_next_exptime(cam_name, elapsed_time)
        return next_exptimes

    def _get_next_exptime(self, camera_name, elapsed_time):
        """Calculate the next exposure time for the flat fields, accounting for changes in sky
        brightness.
        Args:
            camera_name (str): The name of the camera.
            elapsed_time (astropy.Quantity): The time between the previous exposure and now.
        Returns:
            astropy.Quantity: The next exposure time.
        """
        # Get data for specific camera
        previous_exptime = self._exptimes[camera_name][-1]
        target_counts = self._target_counts[camera_name]
        average_counts = self._previous_counts[camera_name][-1]

        # Calculate next exptime
        exptime = previous_exptime * (target_counts / average_counts)
        sky_factor = 2.0 ** (elapsed_time / 180.0)
        if self.past_midnight:
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
        counts = []
        for cam_name, filename in filename_dict.items():
            counts[cam_name] = self._get_average_count(cam_name, filename)
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
            data = fits.getdata(filename)
        except FileNotFoundError:
            data = fits.getdata(filename + '.fz')
        data = data.astype('int32')

        # Calculate average counts per pixel
        average_counts, _, _ = sigma_clipped_stats(data - self._biases[cam_name])
        if average_counts < min_counts:
            self.logger.warning('Truncating mean flat-field counts to minimum value: '
                                f'{average_counts}<{min_counts}.')
            average_counts = min_counts

        return average_counts

    def _take_biases(self, seconds=0):
        """ Take a bias exposure for each camera. Should only be run once per sequence.
        Args:
            seconds (optional, float): The exposure time in seconds, default 0.
        """
        events = []
        filenames = {}

        # Take the bias exposures
        for cam_name, camera in self.cameras.items():
            filename = self._get_bias_filename(cam_name)
            event = camera.take_exposure(filename=filename, seconds=seconds, dark=True)
            events.append(event)
            filenames[cam_name] = filename

        # Wait for exposures to complete
        wait_for_events(events, timeout=seconds+self._timeout, sleep_delay=1)

        # Read the biases
        for cam_name, filename in filenames.items():
            self._biases[cam_name] = fits.getdata(filename)

    def _take_darks(self, **kwargs):
        """ Take the dark frames for each camera for each exposure time. This is potentially a
        long-running function, so we need to check safety frequently.
        Args:
            exptimes: dict of camera_name: list of exposure times.
        """
        exptimes = self._exptimes.copy()  # Don't modify original exptimes
        # Exposure time lists may not be the same length for each camera
        while True:
            next_exptimes = {}
            for cam_name in exptimes.keys():
                with suppress(KeyError):
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
        """
        events = []
        filenames = {}
        for cam_name, exptime in exptimes.items():
            cam = self.cameras[cam_name]

            # Create filename
            filename = self._get_exposure_filename(cam)

            # Take exposure and get event
            exptime = exptime.to_value(u.second)
            camera_event = cam.take_observation(self.observation, headers=headers,
                                                filename=filename, exptime=exptime, dark=dark)
            events.apppend(camera_event)
            filenames[cam_name] = filename

        # Block until exposures are complete
        self._wait_for_exposures(events, exptimes)

    def _wait_for_exposures(self, events, exptimes):
        """ Block until exposures have completed.
        Args:
            events: (list of threading.Event): The observation events.
            exptimes (dict): Dict of cam_name: exptime pairs.
        """
        timeout = max(exptimes.values()).to_value(u.second) + self._timeout

        # Block until done exposing on all cameras
        self.logger.debug(f"Waiting for flat-fields with timeout of {timeout}.")
        wait_for_events(events, timeout=timeout, sleep_delay=1)

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
            return True
        return self._safety_func()

    def _count_good_exposures(self):
        """ Count the number of good exposures for each camera.
        Returns:
            dict: cam_name: number pairs.
        """
        number = {}
        for cam_name in self.cameras.keys():
            counts = np.array(self.average_counts[cam_name].values())
            target = self._target_counts[cam_name]
            n_good = abs(counts - target) < self._counts_tolerance[cam_name]
            number[cam_name] = n_good.sum()
        return number
