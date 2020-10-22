from threading import Event
from Pyro5.api import Proxy

event_types = {"camera",
               "focuser",
               "filterwheel"}


class RemoteEvent(Event):
    """Interface for threading.Events of a remote camera or its subcomponents.

    Current supported types are: `camera`, `focuser`, `filterwheel`.
    """

    def __init__(self, uri, event_type):
        super().__init__()
        # Always create a new proxy in case we are running in a thread
        self._proxy = Proxy(uri)
        if event_type not in event_types:
            raise ValueError(f"Event type {event_type} not one of allowed types: {event_types}")
        self._type = event_type

    def set(self):
        print(f"SETTING {self._type} EVENT")
        self._proxy.event_set(self._type)

    def clear(self):
        self._proxy.event_clear(self._type)

    def is_set(self):
        print(f"CHECKING {self._type} EVENT: {self._proxy.event_is_set(self._type)}")
        return self._proxy.event_is_set(self._type)

    def wait(self, timeout=None):
        return self._proxy.event_wait(self._type, timeout)
