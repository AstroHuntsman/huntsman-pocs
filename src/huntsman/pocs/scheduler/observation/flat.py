import os
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation


class FlatFieldObservation(DitheredObservation):
    """ Observation object for flat fields. """

    def __init__(self, *args, **kwargs):
        """
            *args, **kwargs: Parsed to DitheredObservation.__init__
        """
        super().__init__(*args, **kwargs)
        self.directory = os.path.join(self._image_dir, "flat")

    # Methods

    def get_exposure_filename(self, camera):
        """ Get the exposure filename for a camera.
        Args:
            camera (Camera): A camera instance.
        """
        path = os.path.join(self.directory, camera.uid, self.seq_time)
        filename = os.path.join(
            path, f'flat_{self.current_exp_num:03d}.{camera.file_extension}')
        return filename
