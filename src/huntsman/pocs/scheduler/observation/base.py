import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from astropy import units as u

from panoptes.utils.utils import get_quantity_value
from panoptes.pocs.base import PanBase
from huntsman.pocs.scheduler.field import AbstractField, CompoundField


class AbstractObservation(PanBase, ABC):
    """ Abstract base class for Observation objects. """

    def __init__(self, field, exptime=120 * u.second, min_nexp=1, exp_set_size=1, priority=1,
                 dark=False, filter_name=None, directory=None, defocused=False, **kwargs):
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
            min_nexp (int): The minimum number of exposures to be taken. Default: 1.
            exp_set_size (int): Number of exposures to take per set, default: 1.
            defocused (bool): True if the observation should be taken in defocused mode.
                Default False.
        """
        super().__init__(**kwargs)

        if float(priority) <= 0:
            raise ValueError("Priority must be larger than 0.")

        if min_nexp % exp_set_size != 0:
            raise ValueError(f"Minimum number of exposures (min_nexp={min_nexp}) must be "
                             f"a multiple of set size (exp_set_size={exp_set_size}).")

        if not isinstance(field, AbstractField):
            raise ValueError("field must be an instance of AbstractField.")

        self._image_dir = self.get_config('directories.images')
        self._field = field
        self._exptime = exptime
        self._is_defocused = bool(defocused)

        self.merit = 0.0
        self._seq_time = None
        self.exposure_list = OrderedDict()
        self.pointing_images = OrderedDict()

        self.dark = bool(dark)
        self.priority = float(priority)
        self.filter_name = filter_name
        self.min_nexp = int(min_nexp)
        self.exp_set_size = int(exp_set_size)

        if directory is None:
            directory = os.path.join(self._image_dir, "fields", self.field.field_name)
        self.directory = directory

    def __name__(self):
        return self.__class__.__name__

    def __str__(self):
        return f"{self.__name__}: {self._field}: exptime={self.exptime}, filter={self.filter_name}"

    # Abstract properties

    @property
    @abstractmethod
    def field(self):
        """ Return the current Field for this observation.
        Note that this *must* be an instance of huntsman.pocs.scheduler.field.Field, rather than
        e.g. a CompoundField for the scheduler to work correctly.
        Returns:
            huntsman.pocs.scheduler.field.Field: The Field object.
        """
        pass

    @field.setter
    @abstractmethod
    def field(self, field):
        pass

    # Properties

    @property
    def status(self):
        """ Return the observation status.
        Returns:
            dict: Dictionary containing current status of observation
        """
        status = {
            'current_exp': self.current_exp_num,
            'dec_mnt': self.field.coord.dec.value,
            'equinox': self.field.equinox,
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
    def name(self):
        """ Name of the `~pocs.scheduler.field.Field` associated with the observation """
        return self.field.name

    @property
    def exptime(self):
        return self._exptime

    @exptime.setter
    def exptime(self, exptime):
        exptime = get_quantity_value(exptime, u.second) * u.second
        if exptime < 0 * u.second:  # 0 second exposures correspond to bias frames
            raise ValueError(f"Exposure time must be greater than or equal to 0, got {exptime}.")
        self._exptime = exptime

    @property
    def seq_time(self):
        """ The time at which the observation was selected by the scheduler. """
        return self._seq_time

    @seq_time.setter
    def seq_time(self, time):
        self._seq_time = time

    @property
    def current_exp_num(self):
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
            self.logger.warning("No pointing image available.")

    @property
    def minimum_duration(self):
        return self.exptime * self.min_nexp

    @property
    def set_duration(self):
        return self.exptime * self.exp_set_size

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

    @property
    def is_defocused(self):
        return self._is_defocused

    # Methods

    def reset(self):
        """ Resets the exposure information for the observation. """
        self.logger.debug(f"Resetting observation {self}.")
        self.exposure_list = OrderedDict()
        self.merit = 0.0
        self.seq_time = None

    def mark_exposure_complete(self):
        """ Explicitly mark the current exposure as complete. """
        pass


class Observation(AbstractObservation):

    """ A normal observation consisting of a single Field. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return (f"{self.field}: {self.exp_set_size} exposures in blocks of {self.exp_set_size},"
                f" minimum {self.min_nexp}, priority {self.priority:.1f}")

    # Properties

    @property
    def field(self):
        """
        Returns:
            huntsman.pocs.scheduler.field.Field: A Field object.
        """
        return self._field

    @field.setter
    def field(self, field):
        if not isinstance(field, AbstractField):
            raise TypeError(f"field must be a valid Field instance, got {type(field)}.")
        self._field = field


class CompoundObservation(AbstractObservation):
    """ Compound observation class for use with CompoundField objects. Compound observations share
    the same basic attributes e.g. exposure time and filter name.
    """

    def __init__(self, field, batch_size=1, *args, **kwargs):
        """
        Args:
            field (huntsman.pocs.scheduler.field.CompoundField): The CompoundField object.
            batch_size (int, optional): Take this many exposures before moving onto the next
                sub-field. Default: 1.
            **kwargs: Parsed to AbstractObservation.
        """
        if not isinstance(field, CompoundField):
            raise TypeError("field must be an instance of CompoundField.")

        self.batch_size = int(batch_size)

        min_nexp = field.max_subfields * len(field) * self.batch_size
        exp_set_size = min_nexp

        super().__init__(field, min_nexp=min_nexp, exp_set_size=exp_set_size, *args, **kwargs)

    # Properties
    # exposures_per_field = current_exp_num / (len(self._field) * batch_size)

    @property
    def field(self):
        """
        The field is determined by current exposure number, number of sub-fields and batch size.
        Returns:
            huntsman.pocs.scheduler.field.Field: A Field object.
        """
        field_idx = int(self.current_exp_num / self.batch_size) % len(self._field)
        field = self._field[field_idx]

        # Check if the field is nested (i.e. another Compound Field)
        if isinstance(field, CompoundField):

            exposure_list = list(self.exposure_list.keys())
            exposure_step = self.batch_size * len(self._field)

            # Count the number of exposures for this subfield
            # This is a bit tricky and could be improved by having an "update" method
            exposures_this_field = 0
            for i in range(self.batch_size):
                exposure_offset = field_idx * self.batch_size + i
                exposures_this_field += len(exposure_list[exposure_offset::exposure_step])

            # Get the corresponding nested field index
            nested_field_idx = int(exposures_this_field / self.batch_size) % len(field)

            # Returned the nested field
            nested_field = field[nested_field_idx]

            return nested_field

        return field

    @field.setter
    def field(self, field):
        if not isinstance(field, CompoundField):
            raise TypeError("field must be an instance of CompoundField.")
        self._field = field
