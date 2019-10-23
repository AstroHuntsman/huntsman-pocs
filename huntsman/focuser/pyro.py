from pocs.focuser import AbstractFocuser
from huntsman.camera.pyro import Camera


class Focuser(AbstractFocuser):
    """ Class representing the client side interface to the Focuser of a distributed camera. """
    def __init__(self,
                 name='Pyro Focuser',
                 model='pyro',
                 camera=None):

        if not isinstance(camera, Camera):
            msg = f"camera must be instance of huntsman.camera.pyro.Camera, got {type(camera)}."
            raise ValueError

        super().__init__(name=name, model=model, camera=camera)
        self.connect()

##################################################################################################
# Properties
##################################################################################################

    @property
    def is_connected(self):
        """ Is the focuser available """
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
    def is_ready(self):
        return self._proxy.focuser_is_ready

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
