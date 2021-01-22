import os
from astropy import units as u

from panoptes.utils import get_quantity_value
from panoptes.utils import listify

from panoptes.pocs.scheduler.field import Field
from panoptes.pocs.scheduler.observation import Observation


class DarkObservation(Observation):

    """ A Dark observation

    Dark observations will consist of multiple exposure. As the mount will be
    parked when using this class, the fits image header RA, Dec will be centred
    at the parked position.

    Note:
        For now the new observation must be created like a normal `Observation`,
        with one `exptime` and one `field`. Then use direct property assignment
        for the list of `exptime` and `field`. New `field`/`exptime` combos can
        more conveniently be set with `add_field`
    """

    def __init__(self, position, exptimes=None):
        """
        Args:
            position (str): Center of field, can be anything accepted by
                `~astropy.coordinates.SkyCoord`.
        """
        # Set the exposure times
        if exptimes is not None:
            exptimes = listify(exptimes)
        else:
            exptimes = self._get_exptimes_from_config()
        self._exptimes = exptimes

        # Create the observation
        min_nexp = len(self._exptimes)
        exp_set_size = min_nexp
        field = Field('Dark', position=position)
        super().__init__(field=field, min_nexp=min_nexp, exp_set_size=exp_set_size, dark=True)

        # Set initial list to original values
        self._exptimes = listify(self.exptime)

        # Specify directory root for file storage
        self._directory = os.path.join(self._image_dir, 'dark')

    @property
    def exptime(self):
        """ Return current exposure time as a u.Quantity. """
        exptime = self._exptimes[self.current_exp_num]
        return get_quantity_value(exptime, u.second) * u.second

    def __str__(self):
        return f"DarkObservation"
