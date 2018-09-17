# based upon @jamessynge's astrohave.py code in POCS

import time

from pocs.dome.bisque import Dome as BisqueDome
from pocs.dome.abstract_serial_dome import AbstractSerialDome


class Protocol:
    # device names
    SHUTTER = 'Shutter'
    DOOR = 'Door'
    BATTERY = 'Battery'
    SOLAR_ARRAY = 'Solar_A'
    SWITCH = 'Switch'

    # Valid thing to query about status
    VALID_DEVICE = (SHUTTER, DOOR, BATTERY, SOLAR_ARRAY, SWITCH)

    # Commands to send to shutter
    OPEN_DOME = 'Shutter_open'
    CLOSE_DOME = 'Shutter_close'
    KEEP_DOME_OPEN = 'Keep_dome_open'
    GET_STATUS = 'Status_update'
    GET_PARAMETER = 'Get_parameters'

    # Status codes produced by Shutter
    CLOSED = 'Closed'
    OPEN = 'Open'
    OPENING = 'Opening'
    CLOSING = 'Closing'
    PARTIALLY_OPEN = 'PartOpen'
    ILLEGAL = 'Illegal'

    # Status codes produced by the dome when not responding to a movement command.
    STABLE_STATES = (CLOSED, OPEN, PARTIALLY_OPEN)

    # Status codes produced by Door
    DOOR_OPEN = 'Open'
    DOOR_CLOSED = 'Closed'


class HuntsmanDome(AbstractSerialDome, BisqueDome):
    """Class for musca serial shutter control plus sending updated commands to TSX.
    Musca Port setting: 9600/8/N/1

    """
    LISTEN_TIMEOUT = 3  # Max number of seconds to wait for a response.
    MOVE_TIMEOUT = 10  # Max number of seconds to run the door motors.
    MOVE_LISTEN_TIMEOUT = 0.1  # When moving, how long to wait for feedback.
    NUM_CLOSE_FEEDBACKS = 2  # Number of target_feedback bytes needed.

    SHUTTER_CMD_DELAY = 0.5  # s, Wait this long before allowing next command due to slow musica CPU
    STATUS_UPDATE_FREQUENCY = 60.  # s, A status_update is requested every minute to monitor connectivity.
    MIN_OPERATING_VOLTAGE = 11.  # V, so we don't open if less than this or CLose immediately if we go less than this

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

    @property
    def is_open(self):
        v = self._read_latest_state()
        return v == Protocol.OPEN

    def open_dome(self):

        if self.is_open():
            return True

        self.logger.info('Opening dome shutter')
        self._full_move(Protocol.OPEN_DOME, Protocol.OPEN)
        v = self._read_state_until_stable()
        if v == Protocol.OPEN:
            return True
        self.logger.warning('HuntsmanDome.open wrong final state: {!r}', v)
        return False

    def close_dome(self):
        """Short summary.

        Returns
        -------
        type
            Description of returned object.

        """

    @property
    def shutter_status(self):
        """Return a text string describing dome shutter's current status."""
        if not self.is_connected:
            return 'Not connected to the shutter'
        v = self._read_latest_state()
        if v == Protocol.CLOSED:
            return 'Shutter closed'
        if v == Protocol.OPENING:
            return 'Shutter opening'
        if v == Protocol.CLOSING:
            return 'Shutter closing'
        if v == Protocol.OPEN:
            return 'Shutter open'
        if v == Protocol.PARTIALLY_OPEN:
            return 'Shutter partially open'
        if v == Protocol.ILLEGAL:
            return 'Shutter in ILLEGAL state?'
        return 'Unexpected response from Huntsman Shutter Controller: %r' % v

    def __str__(self):
        if self.is_connected:
            return self.status
        return 'Disconnected'

##################################################################################################
# Communication Methods
##################################################################################################


##################################################################################################
# Private Methods
##################################################################################################

    def _read_latest_state(self):
        """Read and return the latest output from the Astrohaven dome controller."""
        # TODO(jamessynge): Add the ability to do a non-blocking read of the available input
        # from self.serial. If there is some input, return it, but don't wait for more. The last
        # received byte is good enough for our purposes... as long as we drained the input buffer
        # before sending a command to the dome.
        self.serial.reset_input_buffer()
        data = self.serial.read()
        if len(data):
            return chr(data[-1])
        return None

    def _read_state_until_stable(self):
        """Read the status until it reaches one of the stable values."""
        end_by = time.time() + HuntsmanDome.LISTEN_TIMEOUT
        c = ''
        while True:
            data = self.serial.read_bytes(size=1)
            if data:
                c = chr(data[-1])
                if c in Protocol.STABLE_STATES:
                    return c
                self.logger.debug('_read_state_until_stable not yet stable: {!r}', data)
            if time.time() < end_by:
                continue
            pass
        return c

    def _full_move(self, send, target_feedback, feedback_countdown=1):
        """Send a command code until the target_feedback is recieved, or a timeout is reached.
        Args:
            send: The command code to send; this is a string of one ASCII character. See
                Protocol above for the command codes.
            target_feedback: The response code to compare to the response from the dome;
                this is a string of one ASCII character. See Protocol above for the codes;
                while the dome is moving, it echoes the command code sent.
        Returns:
            True if the target_feedback is received from the dome before the MOVE_TIMEOUT;
            False otherwise.
        """
        # Set a short timeout on reading, so that we don't open or close slowly.
        # In other words, we'll try to read status, but if it isn't available,
        # we'll just send another command.
        saved_timeout = self.serial.ser.timeout
        self.serial.ser.timeout = HuntsmanDome.MOVE_LISTEN_TIMEOUT
        try:
            have_seen_send = False
            end_by = time.time() + HuntsmanDome.MOVE_TIMEOUT
            self.serial.reset_input_buffer()
            # Note that there is no sleep in this loop because we have a timeout on reading from
            # the the dome controller, and we know that the dome doesn't echo every character that
            # we send to it.
            while True:
                self.serial.write(send)
                data = self.serial.read_bytes(size=1)
                if data:
                    c = chr(data[-1])
                    if c == target_feedback:
                        feedback_countdown -= 1
                        self.logger.debug('Got target_feedback, feedback_countdown={}',
                                          feedback_countdown)
                        if feedback_countdown <= 0:
                            # Woot! Moved the dome and got the desired response.
                            return True
                    elif c == send:
                        have_seen_send = True
                    elif not have_seen_send and c in Protocol.STABLE_STATES:
                        # At the start of looping, we may see the previous stable state until
                        # we start seeing the echo of `send`.
                        pass
                    else:
                        self.logger.warning(
                            'Unexpected value from dome! send={!r} expected={!r} actual={!r}',
                            send, target_feedback, data)
                if time.time() < end_by:
                    continue
                self.logger.error(
                    'Timed out moving the dome. Check for hardware or communications ' +
                    'problem. send={!r} expected={!r} actual={!r}', send, target_feedback, data)
                return False
        finally:
            self.serial.ser.timeout = saved_timeout


# Expose as Dome so that we can generically load by module name, without knowing the specific type
# of dome. But for testing, it make sense to *know* that we're dealing with the correct class.
Dome = HuntsmanDome
