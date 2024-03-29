import random

from panoptes.pocs.dome import AbstractDome


class Dome(AbstractDome):
    """Simulator for a Dome controller."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = 'disconnected'
        self._homed_count = 0
        self.is_parked = False

    @property
    def is_open(self):
        return self._state == 'open'

    @property
    def is_closed(self):
        return self._state == 'closed'

    @property
    def status(self):
        return dict(connected=self.is_connected, open=self._state)

    def connect(self):
        if not self.is_connected:
            self._is_connected = True
            # Pick a random initial state.
            self._state = random.choice(['open', 'closed', 'unknown'])
        return self.is_connected

    def disconnect(self):
        self._is_connected = False
        return True

    def open(self):
        self._state = 'open'
        return self.is_open

    def close(self):
        self._state = 'closed'
        return self.is_closed

    def park(self):
        self._is_parked = True
        return self.is_parked

    def unpark(self):
        self._is_parked = False
        return self.is_parked

    def find_home(self):
        self._homed_count += 1
        return True
