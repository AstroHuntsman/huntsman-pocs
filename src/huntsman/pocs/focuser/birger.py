from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(BirgerFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
