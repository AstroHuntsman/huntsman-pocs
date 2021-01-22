import os
from astropy import units as u

from panoptes.utils.config.client import get_config

from panoptes.pocs.scheduler.field import Field
from panoptes.pocs.scheduler.observation import Observation


class BiasObservation(Observation):
    """
    """

    def __init__(self, position, number=None):
        if number is None:
            number = get_config("calibs.bias.number", default=10)

        # Create a field with no particular coordinates
        field = Field('Bias', position=position)
        super().__init__(field=field, exptime=0 * u.second, min_nexp=number, exp_set_size=number,
                         dark=True)
        # Specify directory root for file storage
        self._directory = os.path.join(self._image_dir, 'bias')

    def __str__(self):
        return f"BiasObservation"
