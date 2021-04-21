import os

from huntsman.pocs.scheduler.field import DitheredField
from huntsman.pocs.scheduler.observation.base import CompoundObservation


class DitheredObservation(CompoundObservation):
    """ Dithered observations consist of multiple `Field` locations with a single exposure time.
    """

    def __init__(self, field, **kwargs):

        if not isinstance(field, DitheredField):
            raise TypeError("field must be an instance of DitheredField.")

        super().__init__(field=field, **kwargs)

    @property
    def directory(self):
        """ Put all dither locations in the same subdirectory. """
        return os.path.join(self._directory, self._field.field_name)
