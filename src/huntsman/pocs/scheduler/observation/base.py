import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from astropy import units as u

from panoptes.utils.utils import get_quantity_value

from panoptes.pocs.base import PanBase
from panoptes.pocs.scheduler.field import Field


class AbstractObservation(PanBase, ABC):
    """ Abstract class for Observations. """

    def __init__(self, priority=1, dark=False, filter_name=None, directory=None, **kwargs):
        """
        Args:
        """
        super().__init__(**kwargs)

        if float(priority) <= 0.0:
            raise ValueError("Priority must be larger than 0.")

        self._image_dir = self.get_config('directories.images')

        self.merit = 0.0
        self._seq_time = None

        self.dark = dark
        self.priority = float(priority)
        self.filter_name = filter_name

        if directory is None:
            directory = self._get_directory()
        self.directory = directory

    # Abstract properties

    @property
    @abstractmethod
    def field(self):
        pass

    @field.setter
    @abstractmethod
    def field(self, field):
        pass

    @property
    @abstractmethod
    def exposure_index(self):
        pass

    @property
    @abstractmethod
    def set_is_finished(self):
        pass

    # Abstract methods

    @abstractmethod
    def reset(self):
        """Resets the exposure information for the observation. """
        pass

    # Abstract private methods
    @abstractmethod
    def _get_directory(self):
        pass

    # Properties

    @property
    def seq_time(self):
        """ The time at which the observation was selected by the scheduler. """
        return self._seq_time

    @seq_time.setter
    def seq_time(self, time):
        self._seq_time = time


class Observation(AbstractObservation):

    def __init__(self, field, exptime=120 * u.second, min_nexp=60, exp_set_size=10, priority=100,
                 **kwargs):
        """ An observation of a given `panoptes.pocs.scheduler.field.Field`.

        An observation consists of a minimum number of exposures (`min_nexp`) that
        must be taken at a set exposure time (`exptime`). These exposures come
        in sets of a certain size (`exp_set_size`) where the minimum number of
        exposures  must be an integer multiple of the set size.
        Note:
            An observation may consist of more exposures than `min_nexp` but
            exposures will always come in groups of `exp_set_size`.
        Args:
            field (pocs.scheduler.field.Field): An object representing the field to be captured.
            exptime (u.second): Exposure time for individual exposures (default 120 * u.second).
            min_nexp (int): The minimum number of exposures to be taken (default: 60).
            exp_set_size (int): Number of exposures to take per set, default: 10.
        """
        super().__init__(**kwargs)

        if not min_nexp % exp_set_size == 0:
            raise ValueError(f"Minimum number of exposures (min_nexp={min_nexp}) must be "
                             f"a multiple of set size (exp_set_size={exp_set_size}).")

        self.field = field
        self.exptime = exptime

        self.min_nexp = min_nexp
        self.exp_set_size = exp_set_size
        self.exposure_list = OrderedDict()
        self.pointing_images = OrderedDict()

        self._min_duration = self.exptime * self.min_nexp
        self._set_duration = self.exptime * self.exp_set_size

        self.reset()

    def __str__(self):
        return "{}: {} exposures in blocks of {}, minimum {}, priority {:.0f}".format(
            self.field, self.exptime, self.exp_set_size, self.min_nexp, self.priority)

    # Properties

    @property
    def status(self):
        """ Observation status

        Returns:
            dict: Dictionary containing current status of observation
        """

        equinox = 'J2000'
        try:
            equinox = self.field.coord.equinox.value
        except AttributeError:  # pragma: no cover
            equinox = self.field.coord.equinox

        status = {
            'current_exp': self.current_exp_num,
            'dec_mnt': self.field.coord.dec.value,
            'equinox': equinox,
            'exp_set_size': self.exp_set_size,
            'exptime': self.exptime.value,
            'field_dec': self.field.coord.dec.value,
            'field_name': self.name,
            'field_ra': self.field.coord.ra.value,
            'merit': self.merit,
            'min_nexp': self.min_nexp,
            'minimum_duration': self.minimum_duration.value,
            'priority': self.priority,
            'ra_mnt': self.field.coord.ra.value,
            'seq_time': self.seq_time,
            'set_duration': self.set_duration.value,
            'dark': self.dark
        }

        return status

    @property
    def exptime(self):
        return self._exptime

    @exptime.setter
    def exptime(self, exptime):
        exptime = get_quantity_value(exptime, u.second) * u.second
        if not exptime >= 0.0 * u.second:  # 0 second exposures correspond to bias frames
            raise ValueError(f"Exposure time must be greater than or equal to 0, got {exptime}.")
        self._exptime = exptime

    @property
    def field(self):
        return self._field

    @field.setter
    def field(self, field):
        if not isinstance(field, Field):
            raise TypeError(f"field must be a valid Field instance, got {type(field)}.")
        self._field = field

    @property
    def minimum_duration(self):
        """ Minimum amount of time to complete the observation """
        return self._min_duration

    @property
    def set_duration(self):
        """ Amount of time per set of exposures """
        return self._set_duration

    @property
    def name(self):
        """ Name of the `~pocs.scheduler.field.Field` associated with the observation """
        return self.field.name

    @property
    def current_exp_num(self):
        """ Return the current number of exposures.

        Returns:
            int: The size of `self.exposure_list`.
        """
        return len(self.exposure_list)

    @property
    def first_exposure(self):
        """ Return the latest exposure information

        Returns:
            tuple: `image_id` and full path of most recent exposure from the primary camera
        """
        try:
            return list(self.exposure_list.items())[0]
        except IndexError:
            self.logger.warning("No exposure available")

    @property
    def last_exposure(self):
        """ Return the latest exposure information

        Returns:
            tuple: `image_id` and full path of most recent exposure from the primary camera
        """
        try:
            return list(self.exposure_list.items())[-1]
        except IndexError:
            self.logger.warning("No exposure available")

    @property
    def pointing_image(self):
        """Return the last pointing image.

        Returns:
            tuple: `image_id` and full path of most recent pointing image from
                the primary camera.
        """
        try:
            return list(self.pointing_images.items())[-1]
        except IndexError:
            self.logger.warning("No pointing image available")

    @property
    def set_is_finished(self):
        """ Check if the current observing block has finished, which is True when the minimum
        number of exposures have been obtained and and integer number of sets have been completed.
        Returns:
            bool: True if finished, False if not.
        """
        # Check the min required number of exposures have been obtained
        has_min_exposures = self.current_exp_num >= self.min_nexp

        # Check if the current set is finished
        this_set_finished = self.current_exp_num % self.exp_set_size == 0

        return has_min_exposures and this_set_finished

    # Methods

    def reset(self):
        """Resets the exposure information for the observation """
        self.logger.debug("Resetting observation {}".format(self))

        self.exposure_list = OrderedDict()
        self.merit = 0.0
        self.seq_time = None

    # Private Methods

    def _get_directory(self):
        return os.path.join(self._image_dir, "fields", self.field.field_name)
