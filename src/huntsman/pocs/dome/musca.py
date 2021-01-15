# based upon @jamessynge's astrohaven.py code in POCS
import threading
import time

import astropy.units as u

from panoptes.utils import CountdownTimer
from panoptes.utils import error
from panoptes.utils import get_quantity_value
from panoptes.pocs.dome.abstract_serial_dome import AbstractSerialDome


class Protocol:
    # device names
    SHUTTER = 'Shutter'
    DOOR = 'Door'
    BATTERY = 'Battery'
    SOLAR_ARRAY = 'Solar_A'
    SWITCH = 'Switch'

    # Valid thing to query about status
    VALID_DEVICE = (SHUTTER, DOOR, BATTERY, SOLAR_ARRAY, SWITCH)

    # Commands to write/send to shutter
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

    # Status codes produced by the dome when not responding to a movement cmd.
    STABLE_STATES = (CLOSED, OPEN, PARTIALLY_OPEN)

    # Status codes produced by Door
    DOOR_OPEN = 'Open'
    DOOR_CLOSED = 'Closed'


class HuntsmanDome(AbstractSerialDome):
    """Class for musca serial shutter control plus sending updated commands to TSX.
    Musca Port setting: 9600/8/N/1

    TODO: See about checking status every 60 seconds to monitor connectivity.

    """
    LISTEN_TIMEOUT = 3  # Max number of seconds to wait for a response.
    MOVE_TIMEOUT = 45  # Max number of seconds to run the door motors.
    MOVE_LISTEN_TIMEOUT = 0.1  # When moving, how long to wait for feedback.
    NUM_CLOSE_FEEDBACKS = 2  # Number of target_feedback bytes needed.

    # s, A status_update is requested every minute to monitor connectivity.
    STATUS_UPDATE_FREQUENCY = 60.
    # V, so we don't open if less than this or CLose immediately if we go less than this
    MIN_OPERATING_VOLTAGE = 12.

    def __init__(self, command_delay=1, max_status_attempts=3, *args, **kwargs):
        """
        Args:
            command_delay (float, optional): Wait this long in seconds before allowing next command
                due to slow musica CPU. Default 1s.
            max_status_attempts (int, optional): If status fails, retry this many times before
                raising a PanError.
        """
        super().__init__(*args, **kwargs)

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

        self._status = dict()
        self._status_delay = 5  # seconds
        self._status_timer = None
        self._close_event = threading.Event()
        self._command_delay = get_quantity_value(command_delay, u.second)
        self._max_status_attempts = int(max_status_attempts)

    @property
    def is_open(self):
        v = self.status[Protocol.SHUTTER]
        return v == Protocol.OPEN

    @property
    def is_closed(self):
        v = self.status[Protocol.SHUTTER]
        return v == Protocol.CLOSED

    @property
    def door_open(self):
        v = self.status[Protocol.DOOR]
        return v == Protocol.DOOR_OPEN

    @property
    def door_closed(self):
        v = self.status[Protocol.DOOR]
        return v == Protocol.DOOR_CLOSED

    @property
    def status(self):
        """A dictionary containing all status info for dome.

        TODO: Add other info (e.g. dome moving)
        TODO: Auto-update this every ~60s
        """
        if self._status_timer is None:
            update_status = True
        else:
            update_status = self._status_timer.expired()

        if update_status:
            for i in range(1, self._max_status_attempts + 1):

                # Attempt to get the status, break out
                status = self._get_shutter_status_dict()
                if all([v in status.keys() for v in Protocol.VALID_DEVICE]):
                    self._status = status
                    break

                # Raise error if max attempts reached
                if i == self._max_status_attempts:
                    raise error.PanError("Unable to retrieve dome status.")

                self.logger.debug(f"Retrying dome status: {i} of {self._max_status_attempts}.")

            self._status_timer = CountdownTimer(self._status_delay)
        return self._status

    def open(self):
        """Open the shutter using musca.

        Returns
        -------
        Boolean
            True if Opened, False if it did not Open.
        """
        if self.is_open:
            return True

        v = self.status[Protocol.BATTERY]
        if v < self.MIN_OPERATING_VOLTAGE:
            self.logger.error(
                'Dome shutter battery voltage too low to open: {!r}', v)
            return False

        self._write_musca(Protocol.OPEN_DOME, 'Opening dome shutter')
        time.sleep(HuntsmanDome.MOVE_TIMEOUT)

        v = self.status[Protocol.SHUTTER]
        if v == Protocol.OPEN:
            # refresh the threading close event
            self._close_event.clear()
            self.logger.info('Starting thread to keep dome open.')
            # start a thread to send the keep dome open command to musca
            keep_open = threading.Thread(target=self.keep_dome_open)
            keep_open.start()
            return True
        self.logger.warning('HuntsmanDome.open wrong final state: {!r}', v)
        return False

    def keep_dome_open(self):
        """Periodically tell musca to reset watchdog timer

        """
        last_time = time.monotonic()
        # maximum shutter open time in seconds
        max_open_seconds = 15 * 60 * 60  # 15 hours in seconds
        for i in range(max_open_seconds):
            # check to see if a dome closure has occured
            if self._close_event.is_set():
                self.logger.info(
                    'Keep dome open thread has detected a dome closure, ending thread.')
                # if dome has closed, don't try to 'keep dome open'
                return
            now = time.monotonic()
            if now - last_time > 290:

                status = self._get_shutter_status_dict()  # Sometimes empty dict
                try:
                    self.logger.info((f'Status Update: Shutter is '
                                      f'{status[Protocol.SHUTTER]}, '
                                      f'Door is {status[Protocol.DOOR]}, '
                                      f'Battery voltage is {status[Protocol.BATTERY]}'))
                except KeyError:
                    self.logger.debug("Failed to get shutter status.")

                self._write_musca(Protocol.KEEP_DOME_OPEN, 'Keeping dome open.')
                last_time = now
                self.logger.debug('Keep dome open thread sleeping for ~5 minutes.')

            time.sleep(1)
        self.logger.warning(
            'Maximum keep dome open loops exceeded. Dome will close in 5 minutes.')

    def close(self):
        """Close the shutter using musca.

        Returns
        -------
        Boolean
            True if Closed, False if it did not Close.
        """
        if self.is_closed:
            return True

        self._close_event.set()
        self._write_musca(Protocol.CLOSE_DOME, 'Closing dome shutter')
        time.sleep(HuntsmanDome.MOVE_TIMEOUT)

        v = self.status[Protocol.SHUTTER]
        if v == Protocol.CLOSED:
            return True
        self.logger.warning('HuntsmanDome.open wrong final state: {!r}', v)
        return False

    def __str__(self):
        if self.is_connected:
            return self._get_shutter_status_string()
        return 'Disconnected'

    def __del__(self):
        self.close()

    ###############################################################################
    # Private Methods
    ###############################################################################

    def _write_musca(self, cmd, log_message=None):
        """Write command to serial bluetooth device musca."""
        if log_message is not None:
            self.logger.info(log_message)
        self.serial.write(f'{cmd}\n')
        time.sleep(self._command_delay)

    def _get_shutter_status_string(self):
        """Return a text string describing dome shutter's current status."""
        if not self.is_connected:
            return 'Not connected to the shutter'
        v = self.status[Protocol.SHUTTER]
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

    def _get_shutter_status_dict(self):
        """ Return dictionary of musca status.

        Example output line:
        # [b'Status:\r\n',
           b'Shutter:Closed\r\n',
           b'Door:Closed\r\n',
           b'Battery:\t 13.0671\r\n',
           b'Solar_A:\t 0.400871\r\n',
           b'Switch:EM243A\r\n']
        """
        self._write_musca(Protocol.GET_STATUS)
        shutter_status_dict = {}
        num_lines = len(Protocol.VALID_DEVICE)
        for i in range(num_lines + 1):  # Add one for the beginning 'Status' key
            k, v = self.serial.read().strip().split(':')
            if k == Protocol.SOLAR_ARRAY or k == Protocol.BATTERY:
                v = float(v)
            if k != 'Status':
                shutter_status_dict[k] = v
        time.sleep(self._command_delay)
        return shutter_status_dict


# Expose as Dome so that we can generically load by module name, without
# knowing the specific type  of dome. But for testing, it make sense to
# *know* that we're dealing with the correct class.
Dome = HuntsmanDome
