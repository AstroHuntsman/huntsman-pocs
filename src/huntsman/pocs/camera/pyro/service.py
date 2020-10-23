import os
import Pyro5.server

from panoptes.utils.config.client import get_config
from panoptes.utils.library import load_module

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.config import get_own_ip
# This import is needed to set up the custom (de)serializers in the same scope
# as the CameraServer and the Camera client's proxy.
from huntsman.pocs.utils.pyro import serializers


@Pyro5.server.expose
@Pyro5.server.behavior(instance_mode="single")
class CameraService(object):
    """A python remote object (pyro) camera service.

    This class should be instantiated on a device that is remote from the
    main POCS control computer.  All logic related to the actual camera
    should exist in a real Camera class and this should merely be used as
    a thin-wrapper that can run on the device.
    """
    _event_locations = {"camera": ("_camera", "_is_exposing_event"),
                        "focuser": ("_camera", "focuser", "_autofocus_event",),
                        "filterwheel": ("_camera", "filterwheel", "_move_event")}

    def __init__(self, device_name=None):
        self.logger = logger
        # Fetch the config once during object creation
        # TODO determine if we want to make all config calls dynamic.
        self.config = get_config()
        self.host = self.config.get('host')
        self.user = os.getenv('PANUSER', 'huntsman')

        # Prepare the camera config
        self.camera_config = self._get_camera_config(device_name)

        camera_model = self.camera_config.get('model')
        self.logger.info(f'Loading module for {camera_model=}')
        module = load_module(camera_model)

        # Create a real instance of the camera
        self._camera = module.Camera(logger=self.logger, **self.camera_config)

        # Set up events for our exposure.
        self._autofocus_event = None

    # Properties - rather than labouriously wrapping every camera property individually expose
    # them all with generic get and set methods.

    def get(self, property_name, subcomponent=None):
        obj = self._camera
        if subcomponent:
            obj = getattr(obj, subcomponent)
        return getattr(obj, property_name)

    def set(self, property_name, value, subcomponent=None):
        obj = self._camera
        if subcomponent:
            obj = getattr(obj, subcomponent)
        setattr(obj, property_name, value)

    @property
    def is_connected(self):
        return self._camera.is_connected

    # Methods

    def get_uid(self):
        """
        Added as an alternative to accessing the uid property because that didn't trigger
        object creation.
        """
        return self._camera.uid

    def take_exposure(self, *args, **kwargs):
        # Start the exposure non-blocking so that camera server can still respond to
        # status requests.
        self._exposure_event = self._camera.take_exposure(blocking=False, *args, **kwargs)

    def autofocus(self, *args, **kwargs):
        # Start the autofocus non-blocking so that camera server can still respond to
        # status requests.
        self._autofocus_event = self._camera.autofocus(blocking=False, *args, **kwargs)

    # Focuser methods - these are used by the remote focuser client, huntsman.focuser.pyro.Focuser

    @property
    def has_focuser(self):
        return self._camera.focuser is not None

    def focuser_move_to(self, position):
        return self._camera.focuser.move_to(position)

    def focuser_move_by(self, increment):
        return self._camera.focuser.move_by(increment)

    # Filterwheel methods - these are used by the remote filterwheel client,
    # huntsman.filterwheel.pyro.FilterWheel

    @property
    def has_filterwheel(self):
        return self._camera.filterwheel is not None

    def filterwheel_move_to(self, position):
        self._camera.filterwheel.move_to(position)

    # Event access

    def _get_event(self, event_type):
        event_location = self._event_locations[event_type]
        obj = self
        for attr_name in event_location:
            obj = getattr(obj, attr_name)
        return obj

    def event_set(self, event_type):
        return self._get_event(event_type).set()

    def event_clear(self, event_type):
        return self._get_event(event_type).clear()

    def event_is_set(self, event_type):
        return self._get_event(event_type).is_set()

    def event_wait(self, event_type, timeout):
        return self._get_event(event_type).wait(timeout)

    def _get_camera_config(self, device_name=None):
        """
        Retrieve the instance-specific camera config from the config server.
        Args:
            device_name (str, optional): The string used to query the config server for the
                instance-specific camera config. If None or not found will attempt to use
                the device's own IP address.
        Returns:
            dict: The camera config dictionary.
        """
        device_configs = self.config.get("cameras")["devices"]

        # Try and use the device name to select the device config
        if device_name is not None:
            for config in device_configs:
                if config["name"] == device_name:
                    self.logger.debug(f"Found camera config by name for {device_name}.")
                    return config

        # If no match for device name, attempt to use IP address
        ip_address = get_own_ip()
        self.logger.debug(f"Querying for camera config with identifier: {ip_address}.")
        try:
            config = device_configs[ip_address]
        except KeyError as err:
            msg = f"Unable to find camera config entry for {ip_address}."
            self.logger.error(msg)
            raise KeyError(msg)
        return config
