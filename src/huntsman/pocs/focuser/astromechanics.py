from panoptes.pocs.focuser.astromechanics import Focuser as AstromechanicsFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(AstromechanicsFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    def __init__(self, *args, **kwargs):
        super().__init__(zero_position=-32768, *args, **kwargs)

    def move_to(self, position):
        """ Moves focuser to a new position.
        Does not do any checking of the requested position but will warn if the lens reports
        hitting a stop.
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
