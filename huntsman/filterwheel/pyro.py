from threading import Event

from pocs.filterwheel import AbstractFilterWheel


class FilterWheelEvent(Event):
    """Interface to the move_event of a remote filterwheel.

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


class FilterWheel(AbstractFilterWheel):
    """ Class representing the client side interface to the Filterwheel of a distributed camera. """
    def __init__(self,
                 name='Pyro Filterwheel',
                 model='pyro',
                 camera=None,
                 **kwargs):

        # Need to get filter names before calling base class constructor.
        filter_names = camera._proxy.filterwheel_filternames
        kwargs['filter_names'] = filter_names
        super().__init__(name=name, model=model, camera=camera, **kwargs)
        self.connect()

##################################################################################################
# Properties
##################################################################################################

    @property
    def is_connected(self):
        """ Is the filterwheel available """
        return self._proxy.filterwheel_is_connected

    @property
    def is_moving(self):
        """ Is the filterwheel currently moving """
        return self._proxy.filterwheel_is_moving

    @property
    def is_ready(self):
        # A filterwheel is 'ready' if it is connected and isn't currently moving.
        return self._proxy.filterwheel_is_ready

    @AbstractFilterWheel.position.getter
    def position(self):
        """ Current integer position of the filter wheel """
        return self._proxy.filterwheel_position

    @AbstractFilterWheel.current_filter.getter
    def current_filter(self):
        """ Name of the filter in the current position """
        return self._proxy.filterwheel_current_filter

    @property
    def is_unidirectional(self):
        return self._proxy.filterwheel_is_unidirectional

##################################################################################################
# Methods
##################################################################################################

    def connect(self):
        # Pyro4 proxy to remote huntsman.camera.pyro.CameraServer instance.
        self._proxy = self.camera._proxy
        # Replace _move_event created by base class constructor with
        # an interface to the remote one.
        self._move_event = FilterWheelEvent(self._proxy)
        # Fetch and locally cache properties that won't change.
        self._name = self._proxy.filterwheel_name
        self._model = self._proxy.filterwheel_model
        self._serial_number = self._proxy.filterwheel_uid

        self.logger.debug(f"{self} connected.")

##################################################################################################
# Private methods
##################################################################################################

    def _move_to(self, position):
        self._proxy.filterwheel_move_to(position)
