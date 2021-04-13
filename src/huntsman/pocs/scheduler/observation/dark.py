import os
from astropy import units as u

from panoptes.utils.utils import get_quantity_value
from panoptes.utils.config.client import get_config

from panoptes.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation


class DarkObservation(Observation):

    def __init__(self, position, exptimes=None, exp_set_size=None, min_nexp=None):
        """
        Args:
            position (str): Center of field, can be anything accepted by
                `~astropy.coordinates.SkyCoord`.
            exptimes (optional): The list of exposure times. If None (default), get from config.
        """
        if exptimes is None:
            exptimes = get_config("calibs.dark.exposure_times", None)
        if exptimes is None:
            raise ValueError("No exposure times provided.")

        self._current_exp_num = 0

        # Create the observation
        field = Field('Dark', position=position)
        super().__init__(field=field, exptime=exptimes, dark=True)

        if exp_set_size is None:
            exp_set_size = len(self._exptime)
        self.exp_set_size = exp_set_size

        if min_nexp is None:
            min_nexp = exp_set_size
        self.min_nexp = min_nexp

        self.directory = os.path.join(self._image_dir, 'dark')

    # Properties

    @property
    def current_exp_num(self):
        return self._current_exp_num

    @property
    def exptime(self):
        exptime = self._exptime[self.current_exp_num]
        return get_quantity_value(exptime, u.second) * u.second

    # Methods

    def mark_exposure_complete(self):
        self._current_exp_num += 1
