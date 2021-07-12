from panoptes.pocs.focuser.astromechanics import Focuser as AstromechanicsFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(AstromechanicsFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
