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
    OPEN_DOME = 'Shutter_open\n'.encode()
    CLOSE_DOME = 'Shutter_close\n'.encode()
    KEEP_DOME_OPEN = 'Keep_dome_open\n'.encode()
    GET_STATUS = 'Status_update\n'.encode()
    GET_PARAMETER = 'Get_parameters\n'.encode()

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

    TODO: See about checking status every 60 seconds to monitor connectivity.

    """
    LISTEN_TIMEOUT = 3  # Max number of seconds to wait for a response.
    MOVE_TIMEOUT = 15  # Max number of seconds to run the door motors.
    MOVE_LISTEN_TIMEOUT = 0.1  # When moving, how long to wait for feedback.
    NUM_CLOSE_FEEDBACKS = 2  # Number of target_feedback bytes needed.

    SHUTTER_CMD_DELAY = 0.5  # s, Wait this long before allowing next command due to slow musica CPU
    STATUS_UPDATE_FREQUENCY = 60.  # s, A status_update is requested every minute to monitor connectivity.
    MIN_OPERATING_VOLTAGE = 12.  # V, so we don't open if less than this or CLose immediately if we go less than this

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.serial.ser.timeout = HuntsmanDome.LISTEN_TIMEOUT

    @property
    def is_open(self):
        v = self._get_shutter_status_dict()[Protocol.SHUTTER]
        return v == Protocol.OPEN

    @property
    def is_closed(self):
        v = self._get_shutter_status_dict()[Protocol.SHUTTER]
        return v == Protocol.CLOSED

    @property
    def door_open(self):
        v = self._get_shutter_status_dict()[Protocol.DOOR]
        return v == Protocol.DOOR_OPEN

    @property
    def door_closed(self):
        v = self._get_shutter_status_dict()[Protocol.DOOR]
        return v == Protocol.DOOR_CLOSED

    def open(self):
        """Open the shutter using musca.

        Returns
        -------
        Boolean
            True if Opened, False if it did not Open.
        """
        if self.is_open():
            return True

        v = self._get_shutter_status_dict()[Protocol.BATTERY]
        if v < self.MIN_OPERATING_VOLTAGE:
            self.logger.error('Dome shutter battery Voltage too low: {!r}', v)
            return False

        _send_musca_command(Protocol.OPEN_DOME, 'Opening dome shutter')
        time.sleep(HuntsmanDome.MOVE_TIMEOUT)

        v = self._get_shutter_status_dict()[Protocol.SHUTTER]
        if v == Protocol.OPEN:
            return True
        self.logger.warning('HuntsmanDome.open wrong final state: {!r}', v)
        return False

    def close(self):
        """Short summary.

        Returns
        -------
        type
            Description of returned object.

        """

    def shutter_status(self):
        """Return a text string describing dome shutter's current status."""
        if not self.is_connected:
            return 'Not connected to the shutter'
        v = self._get_shutter_status_dict()[Protocol.SHUTTER]
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
            return self.shutter_status()
        return 'Disconnected'


##################################################################################################
# Private Methods
##################################################################################################

    def _send_musca_command(self, cmd, log_message=None):
        if log_message is not None:
            self.logger.info(log_message)
        self.serial.ser.write(cmd)
        time.sleep(HuntsmanDome.SHUTTER_CMD_DELAY)

    def _get_shutter_status_dict(self):
        """ Return dictionary of musca status.

        Example output line:
        # # [b'Status:\r\n', b'Shutter:Closed\r\n', b'Door:Closed\r\n', b'Battery:\t 13.0671\r\n',
        b'Solar_A:\t 0.400871\r\n', b'Switch:EM243A\r\n', b'Battery:\t 13.101\r\n',
        b'Solar_A:\t 0.439232\r\n']
        """
        self.serial.ser.write(Protocol.GET_STATUS)
        shutter_status_list = self.serial.ser.readlines()
        shutter_status_dict = {}
        for shutter_status_item in shutter_status_list:
            k, v = shutter_status_item.strip().decode().split(':')
            if k == Protocol.SOLAR_ARRAY or k == Protocol.BATTERY:
                v = float(v)
            shutter_status_dict[k] = v
        time.sleep(HuntsmanDome.SHUTTER_CMD_DELAY)
        return shutter_status_dict


# Expose as Dome so that we can generically load by module name, without knowing the specific type
# of dome. But for testing, it make sense to *know* that we're dealing with the correct class.
Dome = HuntsmanDome
