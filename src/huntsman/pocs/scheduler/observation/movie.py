import numpy as np
from astropy import units as u
from huntsman.pocs.scheduler.field import AbstractField, DitheredField
from huntsman.pocs.scheduler.observation.base import AbstractObservation
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation
from huntsman.pocs.scheduler.observation.flat import FlatFieldObservation
from panoptes.utils.utils import get_quantity_value


class MovieObservation(AbstractObservation):
    """Movie mode observation that inherits from AbstractObservation.
    Adds frame rate, duration and compression parameters.
    """

    def __init__(
        self,
        field,
        frame_rate=5,  # frames per second
        duration=10,  # Total duration of movie
        compression=None,  # FITS compression type
        files_dir=None,
        *args,
        **kwargs,
    ):

        # Store movie-specific parameters
        self.frame_rate = kwargs.pop('frame_rate', frame_rate)  # frames per second
        self.duration = kwargs.pop('duration', duration) * u.second
        self.compression = compression
        self.files_dir = files_dir
        self.max_frames = kwargs.pop(
            'max_frames',
            int(np.ceil(get_quantity_value(self.duration * self.frame_rate))),
        )
        self.mode = kwargs.pop('mode', 'image')
        self.chunking_enabled = kwargs.pop('chunking_enabled', False)

        super().__init__(field, *args, **kwargs)

    def __str__(self):
        return f"{self.field}: {self.duration} duration, {self.frame_rate} fps"


class DitheredMovieObservation(MovieObservation, DitheredObservation):
    """For dithered movie observations"""

    def __init__(self, field, *args, **kwargs):
        if not isinstance(field, DitheredField):
            raise TypeError("field must be an instance of DitheredField")
        super().__init__(field, *args, **kwargs)


class FlatFieldMovieObservation(MovieObservation, FlatFieldObservation):
    """For flat field movie observations"""

    pass
