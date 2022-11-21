from panoptes.pocs.mount.simulator import Mount as SimulatorMount


class Mount(SimulatorMount):
    """ Override class to use Huntsman mount functionality for tests. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def home_and_park(self, *args, home_timeout=None, park_timeout=None, ** kwargs):
        """ Convenience method to first slew to the home position and then park.
        """
        if not self.is_parked:
            # default timeout is 120 seconds but sometimes this isnt enough
            self.slew_to_home(blocking=True, timeout=home_timeout, **kwargs)

            # Reinitialize from home seems to always do the trick of getting us to
            # correct side of pier for parking
            self._is_initialized = False
            self.initialize()
            # default timeout is 120 seconds but sometimes this isnt enough
            self.park(*args, timeout=park_timeout, **kwargs)

            while self.is_slewing and not self.is_parked:
                time.sleep(5)
                self.logger.debug("Slewing to park, sleeping for 5 seconds")

        self.logger.debug("Mount parked")
