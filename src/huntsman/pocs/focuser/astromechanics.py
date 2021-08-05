from math import copysign

from panoptes.utils import error
from panoptes.pocs.focuser.astromechanics import Focuser as AstromechanicsFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(AstromechanicsFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    # The max move is a limitation caused by signed 16-bit integers used by the device
    _max_move = 32767

    def __init__(self, *args, **kwargs):
        super().__init__(zero_position=-32768, *args, **kwargs)

    @AstromechanicsFocuser.position.getter
    def position(self):
        """ Override to return an int, rather than e.g. a np.int64 which breaks Pyro. """
        return int(self._position)

    def move_to(self, position, max_steps=2):
        """ Moves focuser to a new position.
        This function respects the maximum move of the device and will perform multiple moves if
        necessary.
        Args:
            position (int): new focuser position, in encoder units.
            max_steps (int, optional): The maximum number of steps
        Returns:
            int: focuser position following the move, in encoder units.
        """
        # Check the requested position is within the allowable range
        if position > self._max_move:
            raise error.PanError(f"Requested position {position} greater than max for {self}.")
        elif position < -self._max_move - 1:
            raise error.PanError(f"Requested position {position} less than min for {self}.")

        for i in range(max_steps):

            # Calculate the actual move, respecting maximum allowable move
            required_move = position - self.position
            actual_move = copysign(min(abs(required_move), self._max_move), required_move)

            # Do the move and check if we have reached the required position
            # NOTE: This assumes the device reports the exact position
            if self._move_to(self.position + actual_move) == position:
                break

        if self.position != position:
            raise error.PanError(f"{self} did not move to {position} after {max_steps} steps.")

        return self.position

    def _move_to(self, position):
        """ Moves focuser to a new position.
        Args:
            position (int): new focuser position, in encoder units.
        Returns:
            int: focuser position following the move, in encoder units.
        """
        self._is_moving = True
        try:
            self._send_command(f'M{int(position + self._zero_position):d}')
            self._position = position
        finally:
            # Focuser move commands block until the move is finished, so if the command has
            # returned then the focuser is no longer moving.
            self._is_moving = False

        self.logger.debug(f"Moved to encoder position {self.position}")
        return self.position
