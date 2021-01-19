""" Modified focuser to reconnect serial port on command error. """
from panoptes.utils import error
from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser


class Focuser(BirgerFocuser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def reconnect(self):
        """ Close and open serial port and reconnect to focuser. """
        self.logger.debug(f"Attempting to reconnect to {self}.")
        self.__del__()
        self.connect()

    def _send_command(self, *args, **kwargs):
        """ Try command, attempt to reconnect on error and send command again. """
        try:
            return super()._send_command(*args, **kwargs)
        except error.PanError as err:
            self.logger.warning(f"Focuser command failed with exception: {err!r}. Retrying after"
                                " reconnect.")
            self.reconnect()
            return super()._send_command(*args, **kwargs)
