from copy import deepcopy

from astropy import units as u
from panoptes.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation
from panoptes.utils.utils import listify

from huntsman.pocs.utils import dither


class DitheredObservation(Observation):
    """ Dithered observations consist of multiple `Field` locations with a single exposure time.
    """

    def __init__(self, field, pattern=dither.dice9, n_positions=9, dither_offset=0.5 * u.arcmin,
                 random_offset=0.5 * u.arcmin, **kwargs):

        # Setup the dither fields
        dither_coords = dither.get_dither_positions(field.coord, n_positions=n_positions,
                                                    pattern=pattern, pattern_offset=dither_offset,
                                                    random_offset=random_offset)
        fields = [Field(f'FlatDither{i:03d}', c) for i, c in enumerate(dither_coords)]

        # Initialise the observation
        super().__init__(field=fields, min_nexp=n_positions, exp_set_size=n_positions, **kwargs)

    def __str__(self):
        return f"DitheredObservation: {self.field}: {self.exptime}"

    # Properties

    @property
    def field(self):
        return self._field[self.exposure_index]

    @field.setter
    def field(self, field):
        field = listify(field)
        if not all(isinstance(f, Field) for f in field):
            raise TypeError("All fields must be a valid Field instance.")
        self._field = field

    @property
    def exposure_index(self):
        return self.current_exp_num % len(self._field)

    # Methods

    def add_field(self, field):
        """ Add a new field to observe along with exposure time
        Args:
            new_field (pocs.scheduler.field.Field): A `Field` object.
        """
        current_fields = deepcopy(self._field)
        current_fields.extend(field)
        self.field = current_fields
