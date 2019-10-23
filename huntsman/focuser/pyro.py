import astropy.units as u

from pocs.focuser import AbstractFocuser
from pocs.utils import get_quantity_value

class Focuser(AbstractFocuser):
    """ Class representing the client side interface to the Focuser of a distributed camera. """
    def __init__(self,
                 name='Pyro Focuser',
                 model='pyro',
                 camera=None):

        super().__init__(name=name, model=model, camera=camera)
        self.connect()

##################################################################################################
# Properties
##################################################################################################

    @property
    def is_connected(self):
        return self._proxy.focuser_is_connected

    @property
    def position(self):
        """ Current encoder position of the focuser """
        return self._proxy.focuser_position

    @position.setter
    def position(self, position):
        """ Move focusser to new encoder position """
        position = int(position)
        self._proxy.focuser_position = position

    @property
    def min_position(self):
        """ Get position of close limit of focus travel, in encoder units """
        return self._proxy.focuser_min_position

    @property
    def max_position(self):
        """ Get position of far limit of focus travel, in encoder units """
        return self._proxy.focuser_max_position

    @property
    def is_moving(self):
        """ True if the focuser is currently moving. """
        return self._proxy.focuser_is_moving

    @property
    def focuser_autofocus_range(self):
        return self._proxy.focuser_autofocus_range

    @focuser_autofocus_range.setter
    def focuser_autofocus_range(self, autofocus_ranges):
        self._proxy.focuser_autofocus_range = (int(autofocus_range)
                                               for autofocus_range in autofocus_ranges)

    @property
    def focuser_autofocus_step(self):
        return self._proxy.focuser_autofocus_step

    @focuser_autofocus_step.setter
    def focuser_autofocus_step(self, steps):
        self._proxy.focuser_autofocus_step = (int(step) for step in steps)

    @property
    def focuser_autofocus_seconds(self):
        return self._proxy.focuser_autofocus_seconds

    @focuser_autofocus_seconds.setter
    def focuser_autofocus_seconds(self, seconds):
        self._proxy.focuser_autofocus_seconds = float(get_quantity_value(seconds, u.second))

    @property
    def focuser_autofocus_size(self):
        return self._proxy.focuser_autofocus_size

    @focuser_autofocus_size.setter
    def focuser_autofocus_size(self, size):
        self._proxy.focuser_autofocus_size = int(size)

    @property
    def focuser_autofocus_keep_files(self):
        return self._proxy.focuser_autofocus_keep_files

    @focuser_autofocus_keep_files.setter
    def focuser_autofocus_keep_files(self, keep_files):
        self._proxy.focuser_autofocus_keep_files = bool(keep_files)

    @property
    def focuser_autofocus_take_dark(self):
        return self._proxy.focuser_autofocus_take_dark

    @focuser_autofocus_take_dark.setter
    def focuser_autofocus_take_dark(self, take_dark):
        self._proxy.focuser_autofocus_take_dark = bool(take_dark)

    @property
    def focuser_autofocus_merit_function(self):
        return self._proxy.focuser_autofocus_merit_function

    @focuser_autofocus_merit_function.setter
    def focuser_autofocus_merit_function(self, merit_function):
        self._proxy.focuser_autofocus_merit_function = str(merit_function)

    @property
    def focuser_autofocus_merit_function_kwargs(self):
        return self._proxy.focuser_autofocus_merit_function_kwargs

    @focuser_autofocus_merit_function_kwargs.setter
    def focuser_autofocus_merit_function_kwargs(self, kwargs):
        self._proxy.focuser_autofocus_merit_function_kwargs = dict(kwargs)

    @property
    def focuser_autofocus_mask_dilations(self):
        return self._proxy.focuser_autofocus_mask_dilations

    @focuser_autofocus_mask_dilations.setter
    def focuser_autofocus_mask_dilations(self, dilations):
        self._proxy.focuser_autofocus_mask_dilations = int(dilations)

##################################################################################################
# Methods
##################################################################################################

    def connect(self):
        # Pyro4 proxy to remote huntsman.camera.pyro.CameraServer instance.
        self._proxy = self.camera._proxy
        self.name = self._proxy.focuser_name
        self.model = self._proxy.focuser_model
        self.port = self.camera.port
        self._serial_number = self._proxy.focuser_uid
        self.logger.debug(f"{self} connected.")

    def move_to(self, position):
        """ Move focuser to new encoder position """
        position = int(position)
        return self._proxy.focuser_move_to(position)

    def move_by(self, increment):
        """ Move focuser by a given amount """
        increment = int(increment)
        return self._proxy.focuser_move_by(increment)

    def autofocus(self, *args, **kwargs):
        self.camera.autofocus(*args, **kwargs)
