# based upon @jamessynge's astrohave.py code in POCS

import time
import threading

from pocs.utils import CountdownTimer
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

    # s, Wait this long before allowing next command due to slow musica CPU
    SHUTTER_CMD_DELAY = 0.5
    # s, A status_update is requested every minute to monitor connectivity.
    STATUS_UPDATE_FREQUENCY = 60.
    # V, so we don't open if less than this or CLose immediately if we go less than this
    MIN_OPERATING_VOLTAGE = 12.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

        self._status = dict()
        self._status_delay = 5  # seconds
        self._status_timer = CountdownTimer(self._status_delay)
        self._close_event = threading.Event()

    @property
    def is_open(self):
        v = self.status()[Protocol.SHUTTER]
        return v == Protocol.OPEN

    @property
    def is_closed(self):
        v = self.status()[Protocol.SHUTTER]
        return v == Protocol.CLOSED

    @property
    def door_open(self):
        v = self.status()[Protocol.DOOR]
        return v == Protocol.DOOR_OPEN

    @property
    def door_closed(self):
        v = self.status()[Protocol.DOOR]
        return v == Protocol.DOOR_CLOSED

    def status(self):
        """A dictionary containing all status info for dome.

        TODO: Add other info (e.g. dome moving)
        TODO: Auto-update this every ~60s
        """
        if self._status_timer.expired():
            self._status = self._get_shutter_status_dict()
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

        v = self.status()[Protocol.BATTERY]
        if v < self.MIN_OPERATING_VOLTAGE:
            self.logger.error('Dome shutter battery voltage too low to open: {!r}', v)
            return False

        self._write_musca(Protocol.OPEN_DOME, 'Opening dome shutter')
        time.sleep(HuntsmanDome.MOVE_TIMEOUT)

        v = self.status()[Protocol.SHUTTER]
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
        # maximum number of loops before dome closure (correspond to 15hrs)
        max_loops = 186
        for i in range(max_loops):
            # check to see if a dome closure has occured
            if self._close_event.is_set():
                self.logger.info('Keep dome open thread has detected a dome closure, ending thread.')
                # if dome has closed, don't try to 'keep dome open'
                break
            status = self._get_shutter_status_dict()
            self.logger.info((f'Status Update: Shutter is {status[Shutter]}, '
                              f'Door is {status[Door]}, '
                              f'Battery voltage is {status[Battery]}'))
            self.logger.info('Sending keep dome open command to musca.')
            self._write_musca(Protocol.KEEP_DOME_OPEN, 'Keeping dome open.')
            # wait slightly less than 5 minutes to make sure we reset the
            # dome closure timer before it initiates a dome closure
            self.logger.debug('Keep dome open thread sleeping for ~5 minutes.')
            time.sleep(290)
        self.logger.warning('Maximum keep dome open loops exceeded. Dome will close in 5 minutes.')

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

        v = self.status()[Protocol.SHUTTER]
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
        self.serial.ser.write('{}\n'.format(cmd).encode())
        time.sleep(HuntsmanDome.SHUTTER_CMD_DELAY)

    def _read_musca(self, log_message=None):
        """Read serial bluetooth device musca."""
        if log_message is not None:
            self.logger.info(log_message)
        lines = self.serial.ser.readlines()
        time.sleep(HuntsmanDome.SHUTTER_CMD_DELAY)
        return lines

    def _get_shutter_status_string(self):
        """Return a text string describing dome shutter's current status."""
        if not self.is_connected:
            return 'Not connected to the shutter'
        v = self.status()[Protocol.SHUTTER]
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
        # # [b'Status:\r\n', b'Shutter:Closed\r\n', b'Door:Closed\r\n',
        b'Battery:\t 13.0671\r\n',
        b'Solar_A:\t 0.400871\r\n', b'Switch:EM243A\r\n',
        b'Battery:\t 13.101\r\n',
        b'Solar_A:\t 0.439232\r\n']
        """
        self._write_musca(Protocol.GET_STATUS)
        shutter_status_list = self._read_musca()
        shutter_status_dict = {}
        for shutter_status_item in shutter_status_list:
            k, v = shutter_status_item.strip().decode().split(':')
            if k == Protocol.SOLAR_ARRAY or k == Protocol.BATTERY:
                v = float(v)
            shutter_status_dict[k] = v
        time.sleep(HuntsmanDome.SHUTTER_CMD_DELAY)
        return shutter_status_dict


# Expose as Dome so that we can generically load by module name, without
# knowing the specific type  of dome. But for testing, it make sense to
# *know* that we're dealing with the correct class.
Dome = HuntsmanDome
