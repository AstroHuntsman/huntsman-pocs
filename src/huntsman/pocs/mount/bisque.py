""" Minimal overrides to the bisque mount. """
import time

from panoptes.utils import error
from panoptes.pocs.mount.bisque import Mount as BisqueMount
from panoptes.pocs.utils.location import create_location_from_config

from huntsman.pocs.utils.logger import get_logger


def create_mount(**kwargs):
    """ Placeholder until the normal function is working from POCS. """
    location = create_location_from_config()['earth_location']
    return Mount(location=location, **kwargs)


class Mount(BisqueMount):

    def __init__(self, *args, **kwargs):

        logger = get_logger()

        super().__init__(logger=logger, *args, **kwargs)

    def slew_to_target(self, *args, **kwargs):
        """
        Override method to make sure telescope is not moving or tracking before slewing
        to target. This can otherwise be problematic if the dome decides to move itself when
        the slew command is given.
        """
        if self.is_slewing:
            raise error.PanError("Attempted to slew to target but mount is already slewing.")

        self.logger.debug("Deactivating tracking before slewing to target.")
        self.query('stop_moving')
        self.query('stop_tracking')
        time.sleep(10)

        return super().slew_to_target(*args, **kwargs)

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
