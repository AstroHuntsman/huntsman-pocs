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
