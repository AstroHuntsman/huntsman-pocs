class FilterWheelEvent(Event):
    """Interface for threading.Events of a remote camera or its subcomponents (e.g. filterwheel)

    Methods of the AbstractFilterWheel base class make use of a _move_event. In order
    for those methods to work with a Pyro filterwheel we need to replace that Event with
    an inteface to the event of the remote filterwheel.
    """
    def __init__(self, proxy):
        self._proxy = proxy

    def set(self):
        self._proxy.filterwheel_event_set()

    def clear(self):
        self._proxy.filterwheel_event_clear()

    def is_set(self):
        return self._proxy.filterwheel_event_is_set()

    def wait(self, timeout=None):
        return self._proxy.filterwheel_event_wait(timeout)
