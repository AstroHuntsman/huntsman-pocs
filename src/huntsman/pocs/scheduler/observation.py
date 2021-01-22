import os
from contextlib import suppress

from astropy import units as u
from huntsman.pocs.utils import dither
from panoptes.pocs.scheduler.field import Field
from panoptes.pocs.scheduler.observation import Observation
from panoptes.utils import listify


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


class DitheredFlatObservation(DitheredObservation):
    """ A DitheredObservation specifically for flat fields."""

    def __init__(self, position, pattern=dither.dice9, n_positions=9,
                 dither_offset=0.5 * u.arcmin, random_offset=0.5 * u.arcmin,
                 *args, **kwargs):
        """
        Args:
            position (str or astropy.coordinates.SkyCoord): Center of field, can
                be anything accepted by `astropy.coordinates.SkyCoord`.
        """
        # Create the observation

        # Convert from SkyCoord if required.
        with suppress(AttributeError):
            position = position.to_string('hmsdms')  # noqa

        field = Field('Flat Field', position)

        field = Field('Flat Field', position)
        super().__init__(field=field, *args, **kwargs)

        # Listify the exposure time
        self.exptime = [self.exptime for _ in range(n_positions)]

        # Setup the dither fields
        dither_coords = dither.get_dither_positions(
            field.coord, n_positions=n_positions, pattern=pattern,
            pattern_offset=dither_offset, random_offset=random_offset)
        self.field = [Field(f'FlatDither{i:02d}', c) for i, c in enumerate(dither_coords)]

        # Setup attributes for the scheduler
        self.min_nexp = n_positions
        self.exp_set_size = n_positions

        # Specify directory root for file storage
        self._directory = os.path.join(self._image_dir, 'flats')

    def get_exposure_filename(self, camera):
        """ Get the exposure filename for a camera.
        Args:
            camera (Camera): A camera instance.
        """
        path = os.path.join(self.directory, camera.uid, self.seq_time)
        filename = os.path.join(
            path, f'flat_{self.current_exp_num:03d}.{camera.file_extension}')
        return filename
