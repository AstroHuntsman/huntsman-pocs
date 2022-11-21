from panoptes.pocs.mount.simulator import Mount as SimulatorMount
from huntsman.pocs.mount.bisque import HuntsmanMount


class Mount(SimulatorMount, HuntsmanMount):
    """ Override class to use Huntsman mount functionality for tests. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
