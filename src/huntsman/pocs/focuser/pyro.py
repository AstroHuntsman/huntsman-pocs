from panoptes.pocs.focuser import AbstractFocuser


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
        return self._proxy.get("position", "focuser")

    @position.setter
    def position(self, position):
        """ Move focusser to new encoder position """
        self._proxy.set("position", position, "focuser")

    @property
    def min_position(self):
        """ Get position of close limit of focus travel, in encoder units """
        return self._proxy.get("min_position", "focuser")

    @property
    def max_position(self):
        """ Get position of far limit of focus travel, in encoder units """
        return self._proxy.get("max_position", "focuser")

    @property
    def is_connected(self):
        """ Is the filterwheel available """
        return self._proxy.get("is_connected", "focuser")

    @property
    def is_moving(self):
        """ True if the focuser is currently moving. """
        return self._proxy.get("is_moving", "focuser")

    @property
    def is_ready(self):
        return self._proxy.get("is_ready", "focuser")

    @property
    def autofocus_range(self):
        return self._proxy.get("autofocus_range", "focuser")

    @autofocus_range.setter
    def autofocus_range(self, autofocus_ranges):
        self._proxy.set("autofocus_range", autofocus_ranges, "focuser")

    @property
    def autofocus_step(self):
        return self._proxy.get("autofocus_step", "focuser")

    @autofocus_step.setter
    def autofocus_step(self, steps):
        self._proxy.set("autofocus_step", steps, "focuser")

    @property
    def autofocus_seconds(self):
        return self._proxy.get("autofocus_seconds", "focuser")

    @autofocus_seconds.setter
    def autofocus_seconds(self, seconds):
        self._proxy.set("autofocus_seconds", seconds, "focuser")

    @property
    def autofocus_size(self):
        return self._proxy.get("autofocus_size", "focuser")

    @autofocus_size.setter
    def autofocus_size(self, size):
        self._proxy.set("autofocus_size", size, "focuser")

    @property
    def autofocus_keep_files(self):
        return self._proxy.get("autofocus_keep_files", "focuser")

    @autofocus_keep_files.setter
    def autofocus_keep_files(self, keep_files):
        self._proxy.set("autofocus_keep_files", keep_files, "focuser")

    @property
    def autofocus_take_dark(self):
        return self._proxy.get("autofocus_take_dark", "focuser")

    @autofocus_take_dark.setter
    def autofocus_take_dark(self, take_dark):
        self._proxy.set("autofocus_take_dark", take_dark, "focuser")

    @property
    def autofocus_merit_function(self):
        return self._proxy.get("autofocus_merit_function", "focuser")

    @autofocus_merit_function.setter
    def autofocus_merit_function(self, merit_function):
        self._proxy.set("autofocus_merit_function", merit_function, "focuser")

    @property
    def autofocus_merit_function_kwargs(self):
        return self._proxy.get("autofocus_merit_function_kwargs", "focuser")

    @autofocus_merit_function_kwargs.setter
    def autofocus_merit_function_kwargs(self, kwargs):
        self._proxy.set("autofocus_merit_function_kwargs", kwargs, "focuser")

    @property
    def autofocus_mask_dilations(self):
        return self._proxy.get("autofocus_mask_dilations", "focuser")

    @autofocus_mask_dilations.setter
    def autofocus_mask_dilations(self, dilations):
        self._proxy.set("autofocus_mask_dilations", dilations, "focuser")

    ##################################################################################################
    # Methods
    ##################################################################################################

    def connect(self):
        # Pyro4 proxy to remote huntsman.camera.pyro.CameraService instance.
        self._proxy = self.camera._proxy
        self.name = self._proxy.get("name", "focuser")
        self.model = self._proxy.get("model", "focuser")
        self.port = self.camera.port
        self._serial_number = self._proxy.get("uid", "focuser")
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
