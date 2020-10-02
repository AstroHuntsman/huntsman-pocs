import os
import requests
from warnings import warn
from threading import Timer
from contextlib import suppress

from astropy import units as u
import Pyro4
import Pyro4.util
import Pyro4.errors

from pocs.utils import load_module
from pocs.utils import get_quantity_value
from pocs.utils import error
from pocs.camera import AbstractCamera

from huntsman.pocs.focuser.pyro import Focuser as PyroFocuser
from huntsman.pocs.filterwheel.pyro import FilterWheel as PyroFilterWheel
from huntsman.pocs.utils.pyro.event import RemoteEvent
# This import is needed to set up the custom (de)serializers in the same scope
# as the CameraServer and the Camera client's proxy.
from huntsman.pocs.utils.pyro import serializers
from huntsman.pocs.utils.config import load_device_config, query_config_server


class Camera(AbstractCamera):
    """
    Class representing the client side interface to a distributed camera
    """

    def __init__(self,
                 uri,
                 name='Pyro Camera',
                 model='pyro',
                 port=None,
                 *args, **kwargs):
        super().__init__(name=name, port=port, model=model, *args, **kwargs)
        self._uri = uri

        # Obtain the NGAS server IP
        if 'ngas_ip' not in self.config.keys():
            self.config['ngas_ip'] = query_config_server(key='control')['ip_address']

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

    @property
    def is_temperature_stable(self):
        return self._proxy.get("is_temperature_stable")

    @property
    def is_ready(self):
        '''
        True if camera is ready to start another exposure, otherwise False.
        '''
        return self._proxy.get("is_ready")

# Methods

    def connect(self):
        """
        (re)connect to the distributed camera.
        """
        self.logger.debug('Connecting to {} at {}'.format(self.port, self._uri))

        # Get a proxy for the camera
        try:
            self._proxy = Pyro4.Proxy(self._uri)
        except Pyro4.errors.NamingError as err:
            msg = "Couldn't get proxy to camera {}: {}".format(self.port, err)
            warn(msg)
            self.logger.error(msg)
            return

        # Set sync mode
        Pyro4.asyncproxy(self._proxy, asynchronous=False)

        # Force camera proxy to connect by getting the camera uid.
        # This will trigger the remote object creation & (re)initialise the camera & focuser,
        # which can take a long time with real hardware.

        uid = self._proxy.get_uid()
        if not uid:
            msg = "Couldn't connect to {} on {}!".format(self.name, self._uri)
            warn(msg)
            self.logger.error(msg)
            return

        # Retrieve and locally cache camera properties that won't change.
        self._serial_number = uid
        self.name = self._proxy.get("name")
        self.model = self._proxy.get("model")
        self._readout_time = self._proxy.get("readout_time")
        self._file_extension = self._proxy.get("file_extension")
        self._is_cooled_camera = self._proxy.get("is_cooled_camera")
        self._filter_type = self._proxy.get("filter_type")

        # Set up proxy for remote camera's _exposure_event
        self._exposure_event = RemoteEvent(self._proxy, event_type="camera")

        self._connected = True
        self.logger.debug("{} connected".format(self))

        if self._proxy.has_focuser:
            self.focuser = PyroFocuser(camera=self)
        else:
            self.focuser = None

        if self._proxy.has_filterwheel:
            self.filterwheel = PyroFilterWheel(camera=self)
        else:
            self.filterwheel = None

    def take_exposure(self,
                      seconds=1.0 * u.second,
                      filename=None,
                      dark=False,
                      blocking=False,
                      *args,
                      **kwargs):
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
        self._proxy.take_exposure(seconds=seconds,
                                  filename=filename,
                                  dark=bool(dark),
                                  *args,
                                  **kwargs)

        max_wait = get_quantity_value(seconds, u.second) + self.readout_time + self._timeout
        self._run_timeout("exposure", blocking, max_wait)

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

        # Proxy for remote _autofocus_event
        self._autofocus_event = RemoteEvent(self._proxy, event_type="focuser")

        # In general it's very complicated to work out how long an autofocus should take
        # because parameters can be set here or come from remote config. For now just make
        # it 5 minutes.
        max_wait = 300
        self._run_timeout("autofocus", blocking, max_wait)

        return self._autofocus_event

# Private Methods

    def _start_exposure(self, seconds=None, filename=None, dark=False, header=None):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _readout(self, filename=None):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _run_timeout(self, timeout_type, blocking, max_wait):
        relevant_event = getattr(self, f"_{timeout_type}_event")
        if blocking:
            success = relevant_event.wait(timeout=max_wait)
            if not success:
                self._timeout_response(timeout_type, relevant_event)
        else:
            # If the remote operation fails after starting in such a way that the event doesn't
            # get set then calling code could wait forever. Have a local timeout thread
            # to be safe.
            timeout_thread = Timer(interval=max_wait,
                                   function=self._timeout_response,
                                   args=(timeout_type, relevant_event))
            timeout_thread.start()

    def _timeout_response(self, timeout_type, timeout_event):
        # This could do more thorough checks for success, e.g. check is_exposing property,
        # check for existence of output file, etc. It's supposed to be a last resort though,
        # and most problems should be caught elsewhere.
        is_set = True
        # Can get a comms error if everything has finished and shutdown before the timeout,
        # e.g. when running tests.
        with suppress(Pyro4.errors.CommunicationError):
            is_set = timeout_event.is_set()
        if not is_set:
            timeout_event.set()
            raise error.Timeout(f"Timeout waiting for blocking {timeout_type} on {self}.")

    def _process_fits(self, file_path, info):
        '''
        Override _process_fits, called by process_exposure in take_observation.

        The difference is that we do an NGAS push following the processing.
        '''
        # Call the super method
        result = super()._process_fits(file_path, info)

        # Do the NGAS push
        self._ngas_push(file_path, info)

        return result

    def _ngas_push(self, filename, metadata, filename_ngas=None, port=7778):
        '''
        Parameters
        ----------
        filename (str):
            The name of the local file to be pushed.
        metadata:
            A dict-like object containing metadata to build the NGAS filename.
        filename_ngas (str, optional):
            The NGAS filename. If None, auto-assign based on metadata.
        port (int, optional):
            The port of the NGAS server. Defaults to the TCP port.

        '''
        # Define the NGAS filename
        if filename_ngas is None:
            extension = os.path.splitext(filename)[-1]
            filename_ngas = f"{metadata['image_id']}{extension}"

        # Get the IP address of the NGAS server
        ngas_ip = self.config['ngas_ip']

        # Post the file to the NGAS server
        url = f'http://{ngas_ip}:{port}/QARCHIVE?filename={filename_ngas}&ignore_arcfile=1'
        with open(filename, 'rb') as f:

            self.logger.info(
                f'Pushing {filename} to NGAS as {filename_ngas}: {url}')

            try:
                # Post the file
                r = requests.post(url, data=f)

                self.logger.debug(f'NGAS response: {r.text}')

                # Confirm success
                r.raise_for_status()

            except Exception as e:
                self.logger.error(f'Error while performing NGAS push: {e}')
                raise(e)


@Pyro4.expose
@Pyro4.behavior(instance_mode="single")
class CameraServer(object):
    """
    Wrapper for the camera class for use as a Pyro camera server
    """
    _event_locations = {"camera": ("_exposure_event",),
                        "focuser": ("_autofocus_event",),
                        "filterwheel": ("_camera", "filterwheel", "_move_event")}

    def __init__(self, config_files=None):
        # Pyro classes ideally have no arguments for the constructor. Do it all from config file.
        self.config = load_device_config(config_files=config_files)
        self.host = self.config.get('host')
        self.user = os.getenv('PANUSER', 'huntsman')

        camera_config = self.config.get('camera')
        camera_config.update({'config': self.config})

        module = load_module('pocs.camera.{}'.format(camera_config['model']))
        self._camera = module.Camera(**camera_config)

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
        kwargs['blocking'] = False
        self._exposure_event = self._camera.take_exposure(*args, **kwargs)

    def autofocus(self, *args, **kwargs):
        # Start the autofocus non-blocking so that camera server can still respond to
        # status requests.
        kwargs['blocking'] = False
        self._autofocus_event = self._camera.autofocus(*args, **kwargs)

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
        self._camera.filterwheel._move_to(position)

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
