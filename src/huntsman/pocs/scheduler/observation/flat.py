import os
from contextlib import suppress

from astropy import units as u
from huntsman.pocs.utils import dither
from panoptes.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation


class DitheredFlatObservation(DitheredObservation):

    def __init__(self, position, pattern=dither.dice9, n_positions=9, dither_offset=0.5 * u.arcmin,
                 random_offset=0.5 * u.arcmin, *args, **kwargs):
        """
        Args:
            position (str or astropy.coordinates.SkyCoord): Center of field, can
                be anything accepted by `astropy.coordinates.SkyCoord`.
        """
        # Convert from SkyCoord if required
        with suppress(AttributeError):
            position = position.to_string('hmsdms')
        field = Field('Flat', position=position)

        super().__init__(field=field, *args, **kwargs)

        # Listify the exposure time
        self.exptime = [self.exptime] * n_positions

        # Setup the dither fields
        dither_coords = dither.get_dither_positions(field.coord, n_positions=n_positions,
                                                    pattern=pattern, pattern_offset=dither_offset,
                                                    random_offset=random_offset)
        self.field = [Field(f'FlatDither{i:03d}', c) for i, c in enumerate(dither_coords)]

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
