import time

from panoptes.utils import error
from panoptes.utils.time import CountdownTimer

from panoptes.pocs.mount.bisque import Mount as BisqueMount
from panoptes.pocs.utils.location import create_location_from_config

from huntsman.pocs.utils.logger import get_logger


def create_mount(**kwargs):
    """ Placeholder until the normal function is working from POCS. """
    location = create_location_from_config()['earth_location']
    return Mount(location=location, **kwargs)


class Mount(BisqueMount):

    """ Minimal overrides to the Bisque Mount class. """

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

        return self._slew_to_target(*args, **kwargs)

    # Private methods

    def _slew_to_target(self, timeout=180, blocking=True):
        """ Override method to use closed loop slew if necessary. Also improve error handling
        compared to base class.
        """
        if self.is_parked:
            raise RuntimeError("Mount is parked. Cannot slew.")

        if not self.has_target:
            raise RuntimeError("Target Coordinates not set. Cannot slew.")

        mount_coords = self._skycoord_to_mount_coord(self._target_coordinates)

        self.logger.info(f"Slewing to target: {mount_coords}")

        # Check whether we should do a closed loop slew
        # Note that a dynamic config item is used here so it can be changed on the fly
        do_normal_slew = not self.get_config("mount.closed_loop_slew", False)

        if not do_normal_slew:

            # Try doing a closed loop slew
            self.logger.info("Performing closed-loop slew")
            try:
                response = self.query('closed_loop_slew_to_target', timeout=timeout)

            # If something went wrong e.g. with plate solve, try normal slew instead
            except Exception as err:
                self.logger.error(f"Problem with closed loop slew: {err!r}. Trying normal slew.")
                do_normal_slew = True

        # Do a normal slew if necessary
        if do_normal_slew:
            response = self.query('slew_to_coordinates',
                                  params={'ra': mount_coords[0], 'dec': mount_coords[1]},
                                  timeout=timeout)

        # Issue the command
        success = response.get("success", False)

        if not success:
            raise RuntimeError(f"Exception while slewing. Mount response: {response}.")

        # Wait for slew to complete
        if blocking:
            self._wait_for_slew(timeout=timeout)

        # Shouldn't need to return this, but instead rely on Exceptions
        return success

    def _wait_for_slew(self, sleep_time=1, timeout=300):
        """
        """
        # Set up the timeout timer
        self.logger.debug(f'Setting slew timeout timer for {timeout} sec')
        timeout_timer = CountdownTimer(timeout)

        while self.is_tracking is False:

            # Check if timer is expired
            if timeout_timer.expired():
                raise error.Timeout('Timeout while slewing to target.')

            # Sleep
            self.logger.debug(f'Slewing to target, sleeping for {sleep_time} seconds')
            timeout_timer.sleep(max_sleep=sleep_time)

        self.logger.info("Finished slewing to target. Now tracking.")
