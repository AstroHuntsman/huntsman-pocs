import os
from contextlib import suppress

from panoptes.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation


class FlatFieldObservation(DitheredObservation):

    def __init__(self, position, **kwargs):
        """
        Args:
            position (str or astropy.coordinates.SkyCoord): Center of field, can
                be anything accepted by `astropy.coordinates.SkyCoord`.
        """
        # Convert from SkyCoord if required
        with suppress(AttributeError):
            position = position.to_string('hmsdms')
        field = Field('Flat', position=position)

        super().__init__(field=field, **kwargs)

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
