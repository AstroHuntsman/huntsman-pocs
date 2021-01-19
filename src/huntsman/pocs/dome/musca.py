import threading
import time
from threading import Lock

from astropy import units as u

from panoptes.utils import error, get_quantity_value
from panoptes.utils.time import CountdownTimer
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
    MOVE_LISTEN_TIMEOUT = 0.1  # When moving, how long to wait for feedback.
    NUM_CLOSE_FEEDBACKS = 2  # Number of target_feedback bytes needed.

    # s, A status_update is requested every minute to monitor connectivity.
    STATUS_UPDATE_FREQUENCY = 60.
    # V, so we don't open if less than this or CLose immediately if we go less than this
    MIN_OPERATING_VOLTAGE = 12.

    def __init__(self, command_delay=1, max_status_attempts=10, shutter_timeout=100, sleep=120,
                 *args, **kwargs):
        """
        Args:
            command_delay (float, optional): Wait this long in seconds before allowing next command
                due to slow musca CPU. Default 1s.
            max_status_attempts (int, optional): If status fails, retry this many times before
                raising a PanError. Default: 10.
            shutter_timeout (u.Quantity, optional): The dome shutter movement timeout. Default 80s.
            sleep (u.Quantity, optional): Time to sleep between dome loop iterations.
                Default is 2 min.
        """
        super().__init__(*args, **kwargs)
        self._command_lock = Lock()  # Use a lock to make class thread-safe

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

        self._command_delay = get_quantity_value(command_delay, u.second)
        self._shutter_timeout = get_quantity_value(shutter_timeout, u.second)
        self._max_status_attempts = int(max_status_attempts)
        self._sleep = get_quantity_value(sleep, u.second)

        self._keep_open = None

        self.logger.debug("Starting dome control loop.")
        self._stop_dome_thread = False
        self._dome_thread = threading.Thread(target=self._async_dome_loop)
        self._dome_thread.start()

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
    def is_safe_to_open(self):
        v = self.status[Protocol.BATTERY]
        if v < self.MIN_OPERATING_VOLTAGE:
            self.logger.debug('Dome shutter battery voltage too low to open: {!r}', v)
            return False
        return True

    @property
    def status(self):
        """A dictionary containing all status info for dome. """
        with self._command_lock:  # Make status call thread-safe
            for i in range(self._max_status_attempts):
                try:
                    status = self._get_status_dict()
                    status["status_thread_running"] = self._dome_thread.is_alive()
                    status["keep_shutter_open"] = self._keep_open
                    return status
                except Exception as err:
                    self.logger.warning(f"Dome status check {i+1} of {self._max_status_attempts}"
                                        f" failed with exception: {err!r}")

            raise error.PanError("Unable to get dome status: max attempts reached.")

    def open(self):
        """Open the shutter using musca.

        Returns
        -------
        Boolean
            True if Opened, False if it did not Open.
        """
        if self.is_open:
            return True

        if not self.is_safe_to_open:
            raise error.PanError("Tried to open the dome shutter while not safe.")

        self.logger.info("Opening dome shutter.")
        with self._command_lock:
            self._write_musca(Protocol.OPEN_DOME)
        self._wait_for_true(self.is_open)

        if not self.is_open:
            raise error.PanError("Attempted to open the dome shutter but got wrong status:"
                                 f" {self.status[Protocol.SHUTTER]}")
        self._keep_open = True

    def close(self):
        """Close the shutter using musca.
        Returns:
            bool: True if Closed, False if it did not Close.
        """
        self._keep_open = False
        if self.is_closed:
            return True

        self.logger.info("Closing dome shutter.")
        with self._command_lock:
            self._write_musca(Protocol.CLOSE_DOME)
        self._wait_for_true(self.is_closed)

        if not self.is_closed:
            raise error.PanError("Attempted to close the dome shutter but got wrong status:"
                                 f" {self.status[Protocol.SHUTTER]}")

    def __str__(self):
        if self.is_connected:
            return self._get_status_string()
        return 'Disconnected'

    def __del__(self):
        self._stop_dome_thread = True
        self.close()
        self._dome_thread.join()

    ###############################################################################
    # Private Methods
    ###############################################################################

    def _async_dome_loop(self):
        """ Repeatedly check status and keep dome open if necessary. """
        self.logger.debug("Starting dome loop.")
        while True:
            # Check if the thread should terminate
            if self._stop_dome_thread:
                self.logger.debug("Stopping dome loop.")
                return

            # Log the dome status
            self.logger.debug(f"Dome status: {self.status}.")

            # If thread has just started, maintain current dome state
            if self._keep_open is None:
                if self.is_open:
                    self.logger.info("Dome shutter is already open, keeping it that way for now.")
                    self._keep_open = True
                else:
                    self._keep_open = False

            # Check if we need to keep the dome open
            if self._keep_open:
                self.logger.debug("Keeping dome open.")
                with self._command_lock:
                    self._write_musca(Protocol.KEEP_DOME_OPEN)

            time.sleep(self._sleep)

    def _write_musca(self, cmd):
        """Wait for the command lock then write command to serial bluetooth device musca."""
        self.serial.write(f'{cmd}\n')
        time.sleep(self._command_delay)

    def _get_status_string(self):
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

    def _get_status_dict(self, max_reads=None):
        """ Return dictionary of musca status.
        Args:
            max_reads (int, optional): Maximum number of lines to read in order to get the status.
                This is useful because musca seems to send the status of the same component
                several times consecutively. If None (default, use 10*the number of expected lines).
        Returns:
            dict: The dome status.
        """
        if max_reads is None:
            max_reads = 10 * len(Protocol.VALID_DEVICE)

        self._write_musca(Protocol.GET_STATUS)  # Automatically sleeps for self._command_delay

        status = {}
        for i in range(max_reads):
            try:
                k, v = self.serial.read().strip().split(':')
            except ValueError:  # not enough values to unpack
                continue
            if k == Protocol.SOLAR_ARRAY or k == Protocol.BATTERY:
                v = float(v)
            if k != 'Status':
                status[k] = v
            if all([v in status.keys() for v in Protocol.VALID_DEVICE]):
                break
            elif i == max_reads - 1:
                raise error.PanError("Max reads reached while attempting to get dome status.")

        return status

    def _wait_for_true(self, prop, sleep=1):
        """ Wait for a property to evaluate to True. """
        timer = CountdownTimer(self._shutter_timeout)
        while not timer.expired():
            if bool(prop) is True:  # Maybe not necessary
                return
            time.sleep(sleep)
        raise error.Timeout("Timeout while waiting for dome shutter.")


# Expose as Dome so that we can generically load by module name, without
# knowing the specific type  of dome. But for testing, it make sense to
# *know* that we're dealing with the correct class.
Dome = HuntsmanDome
