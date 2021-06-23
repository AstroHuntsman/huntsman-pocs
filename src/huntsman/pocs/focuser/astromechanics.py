from panoptes.pocs.focuser.astromechanics import Focuser as AstromechFocuser

from huntsman.pocs.focuser.serial import HuntsmanSerialFocuser


class Focuser(AstromechFocuser, HuntsmanSerialFocuser):
    def __init__(self, *args, **kwargs):
        """Initialize an AbstractSerialMount for the port defined in the config.
            Opens a connection to the serial device, if it is valid.
        """
        self._position = None
        super().__init__(*args, **kwargs)

    @HuntsmanSerialFocuser.position.getter
    def position(self):
        return int(self._position)

    def move_to(self, new_position):
        """ Override to use panoptes utils serial code. """
        self._is_moving = True
        try:
            self._send_command(f'M{int(new_position):d}#')
            self._position = new_position
        finally:
            # Focuser move commands block until the move is finished, so if the command has
            # returned then the focuser is no longer moving.
            self._is_moving = False

        self.logger.debug(f"Moved to encoder position {self.position}")
        return self.position

    def move_by(self, *args, **kwargs):
        """ Override to set position. """
        self._position = super().move_by(*args, **kwargs)

    def _send_command(self, command):
        """ Override method to use panoptes-utils code. """
        if not self.is_connected:
            self.logger.critical(f"Attempt to send command to {self} when not connected!")
            return

        # Clear the input buffer in case there's anything left over in there.
        self._serial.reset_input_buffer()

        # Send command
        self._serial.write(command + '\r')

        return self._serial.read()

    def _move_zero(self):
        """ Override to set position. """
        super()._move_zero()
        self._position = 0
