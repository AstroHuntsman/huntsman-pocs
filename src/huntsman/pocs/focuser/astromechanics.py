from math import copysign

from panoptes.utils import error
from panoptes.pocs.focuser.astromechanics import Focuser as AstromechanicsFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(AstromechanicsFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    # The max move is a limitation caused by signed 16-bit integers used by the device
    _max_move = 32767

    def __init__(self, *args, **kwargs):
        self._device_position = None  # Gets initialised in self._move_zero
        super().__init__(zero_position=-32768, *args, **kwargs)

    @AstromechanicsFocuser.position.getter
    def position(self):
        """ Return the current position in encoder units. """
        return int(self._device_position - self._zero_position)

    def move_to(self, position, **kwargs):
        """ Moves focuser to a new position in encoder units.
        Args:
            position (int): New focuser position, in device units.
        Returns:
            int: focuser position following the move, in device units.
        """
        if position != self.position:
            device_position = int(position + self._zero_position)
            self._move_to_device_position(device_position, **kwargs)
        return self.position

    def _move_to_device_position(self, device_position, max_steps=2):
        """ Moves focuser to a new position in device units.
        Args:
            device_position (int): New focuser position, in device units.
        Returns:
            int: focuser position following the move, in device units.
        """
        device_position = int(device_position)

        # Check the requested position is within the allowable range
        if device_position > self._max_move:
            raise error.PanError(f"Requested device position {device_position} greater than max for"
                                 f" {self}.")
        elif device_position < -self._max_move - 1:
            raise error.PanError(f"Requested device position {device_position} less than min for"
                                 f" {self}.")

        self._is_moving = True
        try:
            for i in range(max_steps):
                # Calculate the actual move, respecting maximum allowable move
                required_move = device_position - self._device_position
                actual_move = int(copysign(min(abs(required_move), self._max_move), required_move))

                # Do the move and check if we have reached the required position
                self._send_command(f'M{self._device_position + actual_move:d}')
                self._device_position += actual_move

                # Check if we are finished
                if self._device_position == device_position:
                    break
        finally:
            # Focuser move commands block until the move is finished, so if the command has
            # returned then the focuser is no longer moving.
            self._is_moving = False

        # Check the move was completed
        if self._device_position != device_position:
            raise error.PanError(f"{self} did not reach device position {device_position}.")

        self.logger.debug(f"Moved to encoder position {self.position} ({device_position}) in"
                          f" {i + 1} step(s)")

        return self.position

    def _move_zero(self):
        """ Move the focuser to its zero position and set the current position to zero. """
        # Get the current device position from the device itself
        self._device_position = int(self._send_command("P").strip("#"))
        self.logger.debug(f"Current device position on {self}: {self._device_position}")

        # Move to the zero point
        # NOTE: The zero point is applied automatically
        self.logger.debug(f"Setting focus encoder zero point at position={self._zero_position}")
        self._move_to_device_position(self._zero_position)

        # Set the current position to 0
        self.logger.debug(f"Zero point of focuser has been calibrated at {self._zero_position}")
