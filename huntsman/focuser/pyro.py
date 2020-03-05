from pocs.focuser import AbstractFocuser


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
    def position(self):
        """ Current encoder position of the focuser """
        return self._proxy.focuser_position

    @position.setter
    def position(self, position):
        """ Move focusser to new encoder position """
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
    def autofocus_range(self):
        return self._proxy.focuser_autofocus_range

    @autofocus_range.setter
    def autofocus_range(self, autofocus_ranges):
        self._proxy.focuser_autofocus_range = autofocus_ranges

    @property
    def autofocus_step(self):
        return self._proxy.focuser_autofocus_step

    @autofocus_step.setter
    def autofocus_step(self, steps):
        self._proxy.focuser_autofocus_step = steps

    @property
    def autofocus_seconds(self):
        return self._proxy.focuser_autofocus_seconds

    @autofocus_seconds.setter
    def autofocus_seconds(self, seconds):
        self._proxy.focuser_autofocus_seconds = seconds

    @property
    def autofocus_size(self):
        return self._proxy.focuser_autofocus_size

    @autofocus_size.setter
    def autofocus_size(self, size):
        self._proxy.focuser_autofocus_size = size

    @property
    def autofocus_keep_files(self):
        return self._proxy.focuser_autofocus_keep_files

    @autofocus_keep_files.setter
    def autofocus_keep_files(self, keep_files):
        self._proxy.focuser_autofocus_keep_files = keep_files

    @property
    def autofocus_take_dark(self):
        return self._proxy.focuser_autofocus_take_dark

    @autofocus_take_dark.setter
    def autofocus_take_dark(self, take_dark):
        self._proxy.focuser_autofocus_take_dark = take_dark

    @property
    def autofocus_merit_function(self):
        return self._proxy.focuser_autofocus_merit_function

    @autofocus_merit_function.setter
    def autofocus_merit_function(self, merit_function):
        self._proxy.focuser_autofocus_merit_function = merit_function

    @property
    def autofocus_merit_function_kwargs(self):
        return self._proxy.focuser_autofocus_merit_function_kwargs

    @autofocus_merit_function_kwargs.setter
    def autofocus_merit_function_kwargs(self, kwargs):
        self._proxy.focuser_autofocus_merit_function_kwargs = kwargs

    @property
    def autofocus_mask_dilations(self):
        return self._proxy.focuser_autofocus_mask_dilations

    @autofocus_mask_dilations.setter
    def autofocus_mask_dilations(self, dilations):
        self._proxy.focuser_autofocus_mask_dilations = dilations

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
        self._connected = self._proxy.focuser_is_connected

        self.logger.debug(f"{self} connected.")

    def move_to(self, position):
        """ Move focuser to new encoder position """
        return self._proxy.focuser_move_to(position)

    def move_by(self, increment):
        """ Move focuser by a given amount """
        return self._proxy.focuser_move_by(increment)

    def autofocus(self, *args, **kwargs):
        self.camera.autofocus(*args, **kwargs)

    def _set_autofocus_parameters(self, *args, **kwargs):
        """Needed to stop the base class overwriting all the parameters of the remote focuser."""
        pass
