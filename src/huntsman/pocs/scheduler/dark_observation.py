from astropy import units as u
from contextlib import suppress

from panoptes.pocs.scheduler.field import Field
from panoptes.pocs.scheduler.observation import Observation
from panoptes.utils import listify


class DarkObservation(Observation):
    """ A Dark-field observation

    Dark observations will consist of multiple exposure. As the mount will be
    parked when using this class, the fields will be centred at the parked
    position.

    Note:
        For now the new observation must be created like a normal `Observation`,
        with one `exptime` and one `field`. Then use direct property assignment
        for the list of `exptime` and `field`. New `field`/`exptime` combos can
        more conveniently be set with `add_field`
    """

    def __init__(self, position, *args, **kwargs):
        """
        Args:
            position (str): Center of field, can be anything accepted by
                `~astropy.coordinates.SkyCoord`.
        """
        # Create the observation
        dark_field = Field('Dark-Field', position)
        super().__init__(field=dark_field, *args, **kwargs)

        # Set initial list to original values
        self._exptime = listify(self.exptime)
        self._field = listify(self.field)

        self.extra_config = kwargs

    @property
    def exptime(self):
        """ Exposure time of the dark observation as a Quantity instance """
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
        """ Field of dark observation """
        return self._field[self.exposure_index]

    @field.setter
    def field(self, values):
        assert all(isinstance(f, Field) for f in listify(values)), \
            self.logger.error("All fields must be a valid Field instance")

        self._field = listify(values)

    @property
    def exposure_index(self):
        exp_index = 0
        with suppress(AttributeError):
            exp_index = self.current_exp_num % len(self._exptime)

        return exp_index

    def __str__(self):
        return f"DarkObservation: {self._field}: {self._exptime}"
