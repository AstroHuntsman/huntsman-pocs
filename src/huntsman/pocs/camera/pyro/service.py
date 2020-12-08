import os
from threading import Event, Thread
from contextlib import suppress
import Pyro5.server
import subprocess

from panoptes.utils.config.client import get_config
from panoptes.utils.library import load_module
from panoptes.utils.error import PanError

from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.config import get_own_ip
from huntsman.pocs.utils.pyro import serializers  # Required to set up the custom (de)serializers


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
                        "focuser": ("_focus_event",),
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
        self.logger.info(f'Loading module for camera model={camera_model}')
        module = load_module(camera_model)

        # Create a real instance of the camera
        self._camera = module.Camera(logger=self.logger, **self.camera_config)

        # Set up events for our exposure.
        self._readout_thread = Thread()
        self._focus_event = Event()

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

    @property
    def is_reading_out(self):
        return self._readout_thread.is_alive()

    # Methods

    def get_uid(self):
        """
        Added as an alternative to accessing the uid property because that didn't trigger
        object creation.
        """
        return self._camera.uid

    def take_exposure(self, *args, **kwargs):
        """Proxy call to the camera client.

        This method will strip any `blocking` parameter that is passed so Pyro can
        handle the blocking appropriately.
        """
        with suppress(KeyError):
            kwargs.pop("blocking")
        try:
            self._readout_thread = self._camera.take_exposure(*args, **kwargs)
            if kwargs.get("testing_error_reboot"):
                raise PanError("Exposure failed on")
        except PanError as err:
            if "Exposure failed on" in err.msg:
                self.logger.debug(f"Rebooting computer hosting camera {self._camera}")
                if not kwargs.get("testing_error_reboot"):
                    subprocess_args = ["sudo", "reboot", "now"]
                else:
                    subprocess_args = ["sudo", "touch", "/tmp/rebooted"]
                subprocess.run(subprocess_args)
            else:
                # raise all other errors still
                raise err

    def autofocus(self, *args, **kwargs):
        """ Start the autofocus non-blocking so that camera server can still respond to
        status requests.
        """
        with suppress(KeyError):
            kwargs.pop("blocking")
        self._focus_event = self._camera.autofocus(blocking=False, *args, **kwargs)

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

    def filterwheel_move_to(self, new_position, **kwargs):
        self._camera.filterwheel.move_to(new_position, **kwargs)

    # Event access

    def _get_event(self, event_type):
        """ Retrieve an event by event_type from this class or one of its subcomponent.
        Args:
            event_type (str): The event type. Must be listed in `_event_locations`.
        Returns:
            threading.Event: The event.
        """
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
            self.logger.debug(f"Unable to find config entry for {device_name}.")

        # If no match for device name, attempt to use IP address
        ip_address = get_own_ip()
        self.logger.debug(f"Querying for camera config with identifier: {ip_address}.")
        for config in device_configs:
            if config["name"] == ip_address:
                return config

        raise RuntimeError(f"Unable to find camera config entry for {ip_address}.")
