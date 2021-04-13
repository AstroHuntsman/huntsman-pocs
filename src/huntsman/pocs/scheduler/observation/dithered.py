from panoptes.pocs.scheduler.field import DitheredField
from huntsman.pocs.scheduler.observation.base import CompoundObservation


class DitheredObservation(CompoundObservation):
    """ Dithered observations consist of multiple `Field` locations with a single exposure time.
    """

    def __init__(self, field, **kwargs):

        if not isinstance(field, DitheredField):
            raise ValueError("field must be an instance of DitheredField.")

        super().__init__(field=field, **kwargs)

    def __str__(self):
        return f"DitheredObservation: {self.field}: {self.exptime}"
