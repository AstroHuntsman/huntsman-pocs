from threading import Event

event_types = {"camera",
               "focuser",
               "filterwheel"}


class RemoteEvent(Event):
    """Interface for threading.Events of a remote camera or its subcomponents (e.g. filterwheel)
    """
    def __init__(self, proxy, event_type):
        self._proxy = proxy
        if event_type not in event_types:
            raise ValueError(f"Event type {event_type} not one of allowed types: {event_types}")
        self._type = event_type

    def set(self):
        self._proxy.event_set(self._type)

    def clear(self):
        self._proxy.event_clear(self._type)

    def is_set(self):
        return self._proxy.event_is_set(self._type)

    def wait(self, timeout=None):
        return self._proxy.event_wait(self._type, timeout)
