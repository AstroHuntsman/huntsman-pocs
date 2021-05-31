import os
from astropy import units as u

from panoptes.utils.utils import get_quantity_value
from panoptes.utils.config.client import get_config

from huntsman.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation


class DarkObservation(Observation):

    def __init__(self, position, exptimes=None, exp_set_size=None, **kwargs):
        """
        Args:
            position (str): Center of field, can be anything accepted by
                `~astropy.coordinates.SkyCoord`.
            exptimes (optional): The list of exposure times. If None (default), get from config.
            exp_set_size (int): Number of exposures to take per set. If None (default), uses the
                length of exptimes.
        """
        if exptimes is None:
            exptimes = get_config("calibs.dark.exposure_times", None)
        if exptimes is None:
            raise ValueError("No exposure times provided.")

        self._current_exp_num = 0

        if exp_set_size is None:
            exp_set_size = len(exptimes)

        # Create the observation
        field = Field('Dark', position=position)
        super().__init__(field=field, exptime=exptimes, exp_set_size=exp_set_size, dark=True, **kwargs)

        self._directory = os.path.join(self._image_dir, "dark")

    # Properties

    @property
    def directory(self):
        return self._directory

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
