from panoptes.pocs.focuser.simulator import Focuser as SimulatorFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(SimulatorFocuser, HuntsmanFocuser):
    """ Override class to use Huntsman focus functionality for tests. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
