from contextlib import suppress
from threading import Timer
from astropy import units as u
from Pyro5.api import Proxy

from panoptes.pocs.camera import AbstractCamera
from panoptes.utils import get_quantity_value

from huntsman.pocs.filterwheel.pyro import FilterWheel as PyroFilterWheel
from huntsman.pocs.focuser.pyro import Focuser as PyroFocuser
from huntsman.pocs.utils import error
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro.event import RemoteEvent
# This import is needed to set up the custom (de)serializers in the same scope
# as the CameraServer and the Camera client's proxy.
from huntsman.pocs.utils.pyro import serializers


class Camera(AbstractCamera):
    """A python remote object (pyro) camera client.

    This class should be instantiated on the main control computer that is
    running POCS, namely via an `Observatory` object.
    """

    def __init__(self, uri, name='Pyro Camera', model='pyro', port=None, *args, **kwargs):
        self.logger = logger
        # The proxy used for communication with the remote instance.
        self._uri = uri
        self.logger.debug(f'Connecting to {port} at {self._uri}')
        try:
            self._proxy = Proxy(self._uri)
        except error.PyroProxyError as err:
            logger.error(f"Couldn't get proxy to camera on {port=}: {err!r}")
            return

        super().__init__(name=name, port=port, model=model, logger=self.logger, *args, **kwargs)

        # Hardware that may be attached in connect method.
        self.focuser = None
        self.filterwheel = None

        # Connect to camera
        self.connect()

    # Properties

    @property
    def egain(self):
        return self._proxy.get("egain")

    @property
    def bit_depth(self):
        return self._proxy.get("bit_depth")

    @property
    def temperature(self):
        """
        Current temperature of the camera's image sensor.
        """
        return self._proxy.get("temperature")

    @property
    def target_temperature(self):
        """
        Current value of the CCD set point, the target temperature for the camera's
        image sensor cooling control.

        Can be set by assigning an astropy.units.Quantity.
        """
        return self._proxy.get("target_temperature")

    @target_temperature.setter
    def target_temperature(self, target):
        self._proxy.set("target_temperature", target)

    @property
    def temperature_tolerance(self):
        return self._proxy.get("temperature_tolerance")

    @temperature_tolerance.setter
    def temperature_tolerance(self, tolerance):
        with suppress(AttributeError):
            # Base class constructor is trying to set a default temperature temperature
            # before self._proxy exists, & it's up to the remote camera to do that anyway.
            self._proxy.set("temperature_tolerance", tolerance)

    @property
    def cooling_enabled(self):
        """
        Current status of the camera's image sensor cooling system (enabled/disabled).

        For some cameras it is possible to change this by assigning a boolean
        """
        return self._proxy.get("cooling_enabled")

    @cooling_enabled.setter
    def cooling_enabled(self, enabled):
        self._proxy.set("cooling_enabled", bool(enabled))

    @property
    def cooling_power(self):
        """
        Current power level of the camera's image sensor cooling system (typically as
        a percentage of the maximum).
        """
        return self._proxy.get("cooling_power")

    @property
    def is_exposing(self):
        return self._proxy.get("is_exposing")

    @is_exposing.setter
    def is_exposing(self, is_exposing):
        """Setter required by base class."""
        self._proxy.set("is_exposing", is_exposing)

    @property
    def is_temperature_stable(self):
        return self._proxy.get("is_temperature_stable")

    @property
    def is_ready(self):
        """
        True if camera is ready to start another exposure, otherwise False.
        """
        return self._proxy.get("is_ready")

    # Methods

    def connect(self):
        """ Connect to the distributed camera.
        """
        # Force camera proxy to connect by getting the camera uid.
        # This will trigger the remote object creation & (re)initialise the camera & focuser,
        # which can take a long time with real hardware.
        uid = self._proxy.get_uid()
        if not uid:
            self.logger.error(f"Could't connect to {self.name} on {self._uri}, no uid found.")
            return

        # Retrieve and locally cache camera properties that won't change.
        self._serial_number = uid
        self.name = self._proxy.get("name")
        self.model = self._proxy.get("model")
        self._readout_time = self._proxy.get("readout_time")
        self._file_extension = self._proxy.get("file_extension")
        self._is_cooled_camera = self._proxy.get("is_cooled_camera")
        self._filter_type = self._proxy.get("filter_type")

        # Set up proxies for remote camera's events
        self._exposure_event = RemoteEvent(self._uri, event_type="camera")
        self._autofocus_event = RemoteEvent(self._uri, event_type="focuser")

        self._connected = True
        self.logger.debug(f"{self} connected")

        if self._proxy.has_focuser:
            self.focuser = PyroFocuser(camera=self)

        if self._proxy.has_filterwheel:
            self.filterwheel = PyroFilterWheel(camera=self)

    def take_exposure(self, seconds=1.0 * u.second, filename=None, dark=False,
                      blocking=False, *args, **kwargs):
        """Take an exposure for given number of seconds and saves to provided filename.

        Args:
            seconds (u.second, optional): Length of exposure.
            filename (str, optional): Image is saved to this filename.
            dark (bool, optional): Exposure is a dark frame, default False. On cameras that support
                taking dark frames internally (by not opening a mechanical shutter) this will be
                done, for other cameras the light must be blocked by some other means. In either
                case setting dark to True will cause the `IMAGETYP` FITS header keyword to have
                value 'Dark Frame' instead of 'Light Frame'. Set dark to None to disable the
                `IMAGETYP` keyword entirely.
            blocking (bool, optional): If False (default) returns immediately after starting
                the exposure, if True will block until it completes.

        Returns:
            threading.Event: Event that will be set when exposure is complete.
        """
        # Start the exposure
        self.logger.debug(f'Taking {seconds} second exposure on {self}: {filename}')

        # Remote method call to start the exposure
        self._proxy.take_exposure(seconds=seconds, filename=filename, dark=dark, *args, **kwargs)

        max_wait = get_quantity_value(seconds, u.second) + self.readout_time + self._timeout
        self._run_timeout("exposure", "camera", blocking, max_wait)

        return self._exposure_event

    def autofocus(self, blocking=False, *args, **kwargs):
        """
        Focuses the camera using the specified merit function. Optionally performs
        a coarse focus to find the approximate position of infinity focus, which
        should be followed by a fine focus before observing.

        Args:
            seconds (scalar, optional): Exposure time for focus exposures, if not
                specified will use value from config.
            focus_range (2-tuple, optional): Coarse & fine focus sweep range, in
                encoder units. Specify to override values from config.
            focus_step (2-tuple, optional): Coarse & fine focus sweep steps, in
                encoder units. Specify to override values from config.
            thumbnail_size (int, optional): Size of square central region of image
                to use, default 500 x 500 pixels.
            keep_files (bool, optional): If True will keep all images taken
                during focusing. If False (default) will delete all except the
                first and last images from each focus run.
            take_dark (bool, optional): If True will attempt to take a dark frame
                before the focus run, and use it for dark subtraction and hot
                pixel masking, default True.
            merit_function (str, optional): Merit function to use as a
                focus metric, default vollath_F4.
            merit_function_kwargs (dict, optional): Dictionary of additional
                keyword arguments for the merit function.
            mask_dilations (int, optional): Number of iterations of dilation to perform on the
                saturated pixel mask (determine size of masked regions), default 10
            coarse (bool, optional): Whether to perform a coarse focus, otherwise will perform
                a fine focus. Default False.
            make_plots (bool, optional: Whether to write focus plots to images folder, default
                False.
            blocking (bool, optional): Whether to block until autofocus complete, default False.

        Returns:
            threading.Event: Event that will be set when autofocusing is complete

        Raises:
            ValueError: If invalid values are passed for any of the focus parameters.
        """
        if self.focuser is None:
            msg = "Camera must have a focuser for autofocus!"
            self.logger.error(msg)
            raise AttributeError(msg)

        self.logger.debug(f'Starting autofocus on {self}.')

        # Remote method call to start the exposure
        self._proxy.autofocus(*args, **kwargs)

        # In general it's very complicated to work out how long an autofocus should take
        # because parameters can be set here or come from remote config. For now just make
        # it 5 minutes.
        max_wait = 300
        self._run_timeout("autofocus", "focuser", blocking, max_wait)

        return self._autofocus_event

    # Private Methods

    def _start_exposure(self, **kwargs):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _readout(self, **kwargs):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _run_timeout(self, event_name, event_type, blocking, max_wait):
        if blocking:
            event = getattr(self, f"_{event_name}_event")
            success = event.wait(timeout=max_wait)
            if not success:
                self._timeout_response(event_name, event_type, max_wait)
        else:
            # If the remote operation fails after starting in such a way that the event doesn't
            # get set then calling code could wait forever. Have a local timeout thread
            # to be safe.
            timeout_thread = Timer(interval=max_wait, function=self._timeout_response,
                                   args=(event_name, event_type, max_wait))
            timeout_thread.start()

    def _timeout_response(self, event_name, event_type, max_wait):
        # We need an event specific to this thread
        event = RemoteEvent(self._uri, event_type=event_type)
        # This could do more thorough checks for success, e.g. check is_exposing property,
        # check for existence of output file, etc. It's supposed to be a last resort though,
        # and most problems should be caught elsewhere.
        is_set = True
        # TODO error below has changed but this might not apply any more.
        # Can get a comms error if everything has finished and shutdown before the timeout,
        # e.g. when running tests.
        with suppress(error.PyroError):
            is_set = event.is_set()
        if not is_set:
            event.set()
            raise error.Timeout(f"Timeout of {max_wait} reached while waiting for"
                                f" {event_name} on {self}.")


    def _set_cooling_enabled(self):
        """Dummy method required by the abstract class"""
        raise NotImplementedError

    def _set_target_temperature(self):
        """Dummy method required by the abstract class"""
        raise NotImplementedError
