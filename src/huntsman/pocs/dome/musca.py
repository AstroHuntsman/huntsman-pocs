import time
from contextlib import suppress
from threading import Thread, Lock

from astropy import units as u

from panoptes.utils import error
from panoptes.utils.time import CountdownTimer
from panoptes.utils.utils import get_quantity_value

from panoptes.pocs.dome.abstract_serial_dome import AbstractSerialDome as ASDome
from panoptes.pocs.dome.bisque import Dome as BDome

from huntsman.pocs.utils.logger import get_logger


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

    # Types for status values
    STATUS_TYPES = {'Battery': float,
                    "Solar_A": float}


class HuntsmanDome(ASDome, BDome):
    """Class for musca serial shutter control plus sending updated commands to TSX.
    Musca Port setting: 9600/8/N/1

    The default behaviour of the Musca is to asynchronously send status updates when something
    (e.g. battery voltage) changes. A full status update can be requested by sending the appropriate
    command to the musca. However, it appears that musca will not send status updates while the
    shutter is moving, but sends a full status update after it stops moving.

    This class also handles sending park/unpark/find_home requests to TheSkyX which are relayed to
    the domepi via a TheSkyX gRPC plugin.
    """
    LISTEN_TIMEOUT = 3  # Max number of seconds to wait for a response.
    MOVE_LISTEN_TIMEOUT = 0.1  # When moving, how long to wait for feedback.
    NUM_CLOSE_FEEDBACKS = 2  # Number of target_feedback bytes needed.

    # s, A status_update is requested every minute to monitor connectivity.
    STATUS_UPDATE_FREQUENCY = 60.
    # V, so we don't open if less than this or CLose immediately if we go less than this
    MIN_OPERATING_VOLTAGE = 12.

    def __init__(self, max_status_attempts=10, shutter_timeout=100, sleep=60,
                 logger=None, *args, **kwargs):
        """
        Args:
            max_status_attempts (int, optional): If status fails, retry this many times before
                raising a PanError. Default: 10.
            shutter_timeout (u.Quantity, optional): The dome shutter movement timeout. Default 80s.
            sleep (u.Quantity, optional): Time to sleep between dome loop iterations.
                Default is 1 min.
            logger (logger, optional): The logger instance. If not provided, use default Huntsman
                logger.
        """
        if not logger:
            logger = get_logger()

        super().__init__(logger=logger, *args, **kwargs)

        # Explicitly reconnect to the musca device
        # This avoids clashes in the case of multiple dome instances
        self.disconnect()
        time.sleep(5)
        self.connect()

        self._command_lock = Lock()  # Use a lock to make class thread-safe

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

        self._shutter_timeout = get_quantity_value(shutter_timeout, u.second)
        self._max_status_attempts = int(max_status_attempts)
        self._sleep = get_quantity_value(sleep, u.second)

        self._status = {}
        self._keep_open = None
        self._stop_dome_thread = False
        self._stop_status_thread = False
        self._homed_count = 0

        self._status_thread = Thread(target=self._async_status_loop, daemon=True)
        self._dome_thread = Thread(target=self._async_dome_loop, daemon=True)

        # Start the status thread running and wait until we have a complete status reading
        self._status_thread.start()
        self._wait_for_status()
        self.logger.info(f"Got initial dome status: {self.status}")

        # Start the main dome control loop
        self._dome_thread.start()

    def __del__(self):
        self._stop_dome_thread = True
        self.close()
        self._dome_thread.join()
        self._stop_status_thread = True
        self._status_thread.join()
        BDome.__del__(self)

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
            self.logger.debug(f'Dome shutter battery voltage too low to open: {v!r}')
            return False
        return True

    @property
    def status(self):
        """A dictionary containing all status info for dome. """
        return self._status

    @property
    def is_connected(self):
        """  """
        # get the serial property
        serial_connected = ASDome.is_connected.fget(self)
        bdome_connected = BDome.is_connected.fget(self)
        self.logger.info(
            f"Shutter connected: {serial_connected}, TSX dome connected: {bdome_connected}.")
        return serial_connected and bdome_connected

    def connect(self, timeout=10):
        # serial connections
        ASDome.connect(self)
        # TSX connections
        if not BDome.is_connected.fget(self):
            self.write(self._get_command('dome/connect.js'))
            response = self.read()
            self._is_connected = response['success']
        return self.is_connected

    def disconnect(self):
        # serial disconnection
        ASDome.disconnect(self)
        # TSX disconnection
        if BDome.is_connected.fget(self):
            self.write(self._get_command('dome/disconnect.js'))
            response = self.read()
            self._is_connected = not response["success"]
        return not self.is_connected

    def open(self):
        """Open the shutter using musca.
        Returns:
            bool: True if Opened, False if it did not Open.
        """
        if self.is_open:
            return True

        if not self.is_safe_to_open:
            raise error.PanError("Tried to open the dome shutter while not safe.")

        self.logger.info("Opening dome shutter.")
        self._write_musca(Protocol.OPEN_DOME)

        # Wait for the shutter to actually open
        self._wait_for_true("is_open")

        if not self.is_open:
            raise error.PanError("Attempted to open the dome shutter but got wrong status:"
                                 f" {self.status[Protocol.SHUTTER]}")
        self._keep_open = True

    def close(self):
        """ Close the shutter using musca.
        Returns:
            bool: True if Closed, False if it did not Close.
        """
        self._keep_open = False
        if self.is_closed:
            return True

        self.logger.info("Closing dome shutter.")
        self._write_musca(Protocol.CLOSE_DOME)

        # Wait for the it to actually close
        self._wait_for_true("is_closed")

        if not self.is_closed:
            raise error.PanError("Attempted to close the dome shutter but got wrong status:"
                                 f" {self.status[Protocol.SHUTTER]}")

    def park(self, timeout=210):
        if BDome.is_connected.fget(self):
            self.write(self._get_command('dome/park.js'))
            response = self.read(timeout=timeout)

            self._is_parked = response['success']

        return self.is_parked

    def unpark(self, timeout=20):
        if BDome.is_connected.fget(self):
            self.write(self._get_command('dome/unpark.js'))
            response = self.read(timeout=timeout)

            self._is_parked = not response['success']

        return not self.is_parked

    def find_home(self, timeout=210):
        if BDome.is_connected.fget(self):
            self.write(self._get_command('dome/home.js'))
            response = self.read(timeout=timeout)
        if response['success']:
            self._homed_count += 1

        return response['success']

    # Private Methods

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
                self._write_musca(Protocol.KEEP_DOME_OPEN)

            time.sleep(self._sleep)

    def _async_status_loop(self):
        """ Continually read status updates from Musca. """

        # Tell musca to send the full status
        self._write_musca(Protocol.GET_STATUS)

        self.logger.debug("Starting status loop.")
        while True:
            # Check if the thread should terminate
            if self._stop_status_thread:
                self.logger.debug("Stopping status loop.")
                return

            self._status["dome_loop_running"] = self._dome_thread.is_alive()
            self._status["status_loop_running"] = self._status_thread.is_alive()
            self._status["keep_shutter_open"] = self._keep_open

            raw_response = self.serial.read(retry_limit=1, retry_delay=0.1)
            if not raw_response:
                continue

            response = [s.strip() for s in raw_response.split(":")]
            if len(response) != 2:
                continue

            key, value = response
            with suppress(KeyError):
                value = Protocol.STATUS_TYPES[key](value)

            if key in Protocol.VALID_DEVICE:
                self.logger.debug(f"Updating dome status: {key}={value}.")
                self._status[key] = value

    def _write_musca(self, cmd):
        """Wait for the command lock then write command to serial bluetooth device musca."""
        self.logger.debug(f"Writing musca command: {cmd}")
        with self._command_lock:
            self.serial.reset_input_buffer()
            self.serial.write(f'{cmd}\n')

    def _wait_for_status(self, timeout=60, sleep=0.1):
        """ Wait for a complete status.
        Args:
            timeout (float, optional): The timeout in seconds. Default 60.
            sleep (float, optional): Time to sleep between checks in seconds. Default 0.1.
        """
        timer = CountdownTimer(duration=timeout)
        while not timer.expired():
            if all([k in self._status for k in Protocol.VALID_DEVICE]):
                return
            time.sleep(sleep)
        raise error.Timeout("Timeout while waiting for dome shutter status.")

    def _wait_for_true(self, property_name, sleep=1):
        """ Wait for a property to evaluate to True. """
        timer = CountdownTimer(self._shutter_timeout)
        while not timer.expired():
            if getattr(self, property_name):
                return
            time.sleep(sleep)
        raise error.Timeout(f"Timeout while waiting for dome shutter property: {property_name}.")
