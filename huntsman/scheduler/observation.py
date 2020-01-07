from astropy import units as u

from contextlib import suppress
from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation

from pocs.utils import listify


class DitheredObservation(Observation):

    """ Observation that dithers to different points

    Dithered observations will consist of both multiple exposure time as well as multiple
    `Field` locations, which are used as a simple dithering mechanism

    Note:
        For now the new observation must be created like a normal `Observation`,
        with one `exptime` and one `field`. Then use direct property assignment
        for the list of `exptime` and `field`. New `field`/`exptime` combos can
        more conveniently be set with `add_field`
    """

    def __init__(self, *args, **kwargs):
        super(DitheredObservation, self).__init__(*args, **kwargs)

        # Set initial list to original values
        self._exptime = listify(self.exptime)
        self._field = listify(self.field)

        self.extra_config = kwargs

    @property
    def exptime(self):
        exptime = self._exptime[self.exposure_index]

        if not isinstance(exptime, u.Quantity):
            exptime *= u.second

        return exptime

    @exptime.setter
    def exptime(self, values):
        assert all(t > 0.0 for t in listify(values)), \
            self.logger.error("Exposure times (exptime) must be greater than 0")

        self._exptime = listify(values)

    @property
    def field(self):
        return self._field[self.exposure_index]

    @field.setter
    def field(self, values):
        assert all(isinstance(f, Field) for f in listify(values)), \
            self.logger.error("All fields must be a valid Field instance")

        self._field = listify(values)

    @property
    def exposure_index(self):
        _exp_index = 0
        with suppress(AttributeError):
            _exp_index = self.current_exp_num % len(self._exptime)

        return _exp_index

    def add_field(self, new_field, new_exptime):
        """ Add a new field to observe along with exposure time

        Args:
            new_field (pocs.scheduler.field.Field): A `Field` object
            new_exptime (float): Number of seconds to expose

        """
        self.logger.debug("Adding new field {} {}".format(new_field, new_exptime))
        self._field.append(new_field)
        self._exptime.append(new_exptime)

    def __str__(self):
        return "DitheredObservation: {}: {}".format(self._field, self._exptime)


class DarkObservation(Observation):

    """ Collection of darks when weather is bad

    Dark observations will consist of both multiple exposure, but no fields.
    Also, the mount will be parked when used.

    Note:
        For now the new observation must be created like a normal `Observation`,
        with one `exp_time` and one `field`. Then use direct property assignment
        for the list of `exp_time` and `field`. New `field`/`exp_time` combos can
        more conveniently be set with `add_field`
    """

    def __init__(self, *args, **kwargs):
        super(DarkObservation, self).__init__(*args, **kwargs)

        # Set initial list to original values
        self._exp_time = listify(self.exp_time)
        self._field = listify(self.field)

        self.extra_config = kwargs

    @property
    def exp_time(self):
        exp_time = self._exp_time[self.exposure_index]

        if not isinstance(exp_time, u.Quantity):
            exp_time *= u.second

        return exp_time

    @exp_time.setter
    def exp_time(self, values):
        assert all(t > 0.0 for t in listify(values)), \
            self.logger.error("Exposure times (exp_time) must be greater than 0")

        self._exp_time = listify(values)

    @property
    def field(self):
        return self._field[self.exposure_index]

    @field.setter
    def field(self, values):
        assert all(isinstance(f, Field) for f in listify(values)), \
            self.logger.error("All fields must be a valid Field instance")

        self._field = listify(values)

    @property
    def exposure_index(self):
        _exp_index = 0
        with suppress(AttributeError):
            _exp_index = self.current_exp_num % len(self._exp_time)

        return _exp_index

    def __str__(self):
        return "DarkObservation: {}: {}".format(self._field, self._exp_time)
