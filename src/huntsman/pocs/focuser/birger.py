from panoptes.utils import error

from huntsman.pocs.focuser.serial import HuntsmanSerialFocuser
from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser, error_pattern, error_messages


import re
import serial
import glob
from warnings import warn
serial_number_pattern = re.compile(r'^\d{5}$')


class Focuser(BirgerFocuser, HuntsmanSerialFocuser):

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    def __init__(self,
                 name='Birger Focuser',
                 model='Canon EF-232',
                 initial_position=None,
                 port='/dev/tty.USA49*.?',
                 max_command_retries=5,
                 *args, **kwargs):

        self._max_command_retries = max_command_retries

        HuntsmanSerialFocuser.__init__(self, name=name, model=model, port=port, *args, **kwargs)
        self.logger.debug('Initialising Birger focuser')

        if serial_number_pattern.match(self.port):
            # Have been given a serial number
            self.logger.debug('Looking for {} ({})...'.format(self.name, self.port))

            if Focuser._adaptor_nodes is None:
                # No cached device nodes scanning results, need to scan.
                self.logger.debug('Getting serial numbers for all connected Birger focusers')
                Focuser._adaptor_nodes = {}
                # Find nodes matching pattern
                device_nodes = glob.glob(port)

                # Open each device node and see if a Birger focuser answers
                for device_node in device_nodes:
                    try:
                        serial_number = self.connect(device_node)
                        Focuser._adaptor_nodes[serial_number] = device_node
                    except (serial.SerialException, serial.SerialTimeoutException, AssertionError):
                        # No Birger focuser on this node.
                        pass
                    finally:
                        self._serial_port.close()

                if not Focuser._adaptor_nodes:
                    message = 'No Birger focuser devices found!'
                    self.logger.error(message)
                    warn(message)
                    return
                else:
                    self.logger.debug(f'Connected Birger focusers: {Focuser._adaptor_nodes}')

            # Search in cached device node scanning results for serial number
            try:
                device_node = Focuser._adaptor_nodes[self.port]
            except KeyError:
                message = 'Could not find {} ({})!'.format(self.name, self.port)
                self.logger.error(message)
                warn(message)
                return
            self.logger.debug('Found {} ({}) on {}'.format(self.name, self.port, device_node))
            self.port = device_node

        if initial_position is not None:
            self.position = initial_position

    def reconnect(self):
        """ Close and open serial port and reconnect to focuser. """
        self.logger.debug(f"Attempting to reconnect to {self}.")
        self.__del__()
        self.connect(port=self.port)

    def _send_command(self, command, *args, **kwargs):
        """
        Sends a command to the focuser adaptor and retrieves the response.
        Args:
            command (string): command string to send (without newline), e.g. 'fa1000', 'pf'
        Returns:
            list: possibly empty list containing the '\r' terminated lines of the response from the
                adaptor.
        """
        if not self.is_connected:
            self.logger.critical("Attempt to send command to {} when not connected!".format(self))
            return

        # Success variable to verify that the command sent is read by the focuser.
        success = False

        for i in range(self._max_command_retries):
            # Clear the input buffer in case there's anything left over in there.
            self._serial.reset_input_buffer()

            # Send the command
            self._serial.write(command + '\r')
            raw_response = self._serial.read().rstrip().split("\r")

            # In verbose mode adaptor will first echo the command
            echo = raw_response[0]
            if echo != command:
                self.logger.warning(f'echo != command: {echo!r} != {command!r}. Retrying command.')
                continue

            # Adaptor should then send 'OK', even if there was an error.
            ok = raw_response[1]
            if ok != 'OK':
                self.logger.warning(f"ok != 'OK': {ok!r} != 'OK'. Retrying command.")
                continue

            # Depending on which command was sent there may or may not be any further response.
            response = raw_response[2:]
            success = True
            break

        if not success:
            raise error.PanError(f'Failed command {command!r} on {self}')

        # Check for an error message in response
        if response:
            # Not an empty list.
            error_match = error_pattern.match(response[0])
            if error_match:
                # Got an error message! Translate it.
                try:
                    error_message = error_messages[int(error_match.group())]
                    self.logger.error(f"{self} returned error message '{error_message}'!")
                except Exception:
                    self.logger.error(f"Unknown error '{error_match.group()}' from {self}!")

        return response
