import os
import requests
from warnings import warn
from threading import Event
from threading import Timer
from threading import Thread
from contextlib import suppress

from astropy import units as u
import Pyro4
import Pyro4.util

from panoptes.utils import load_module
from panoptes.utils import get_quantity_value
from panoptes.utils import error
from pocs.camera import AbstractCamera

from huntsman.focuser.pyro import Focuser as PyroFocuser
# This import is needed to set up the custom (de)serializers in the same scope
# as the CameraServer and the Camera client's proxy.
from huntsman.utils.pyro import serializers
from huntsman.utils.config import load_device_config, query_config_server

#==============================================================================

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
        self._proxy.egain

    @property
    def bit_depth(self):
        return self._proxy.bit_depth

    @property
    def temperature(self):
        """
        Current temperature of the camera's image sensor.
        """
        return self._proxy.temperature

    @property
    def target_temperature(self):
        """
        Current value of the CCD set point, the target temperature for the camera's
        image sensor cooling control.

        Can be set by assigning an astropy.units.Quantity.
        """
        return self._proxy.target_temperature

    @target_temperature.setter
    def target_temperature(self, target):
        self._proxy.target_temperature = target

    @property
    def temperature_tolerance(self):
        return self._proxy.temperature_tolerance

    @temperature_tolerance.setter
    def temperature_tolerance(self, tolerance):
        with suppress(AttributeError):
            # Base class constructor is trying to set a default temperature temperature
            # before self._proxy exists, & it's up to the remote camera to do that anyway.
            self._proxy.temperature_tolerance = tolerance

    @property
    def cooling_enabled(self):
        """
        Current status of the camera's image sensor cooling system (enabled/disabled).

        For some cameras it is possible to change this by assigning a boolean
        """
        return self._proxy.cooling_enabled

    @cooling_enabled.setter
    def cooling_enabled(self, enabled):
        self._proxy.cooling_enabled = bool(enabled)

    @property
    def cooling_power(self):
        """
        Current power level of the camera's image sensor cooling system (typically as
        a percentage of the maximum).
        """
        return self._proxy.cooling_power

    @property
    def is_exposing(self):
        return not self._exposure_event.is_set()

    @property
    def is_ready(self):
        '''
        True if camera is ready to start another exposure, otherwise False.
        '''
        # First check if exposing, because if so remote camera won't respond to
        # is_ready query until after it has finished.
        if self.is_exposing:
            return False
        return self._proxy.is_ready

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
        self.name = self._proxy.name
        self.model = self._proxy.model
        self._readout_time = self._proxy.readout_time
        self._file_extension = self._proxy.file_extension
        self._is_cooled_camera = self._proxy.is_cooled_camera
        self._filter_type = self._proxy.filter_type
        self._connected = True
        self.logger.debug("{} connected".format(self))

        if self._proxy.has_focuser:
            self.focuser = PyroFocuser(camera=self)
        else:
            self.focuser = None

        self.filterwheel = None  # Remote filterwheels not supported yet.


    def take_exposure(self,
                      seconds=1.0 * u.second,
                      filename=None,
                      dark=False,
                      blocking=False,
                      *args,
                      **kwargs):
        """
        Take exposure for a given number of seconds and saves to provided filename.

        Args:
            seconds (u.second, optional): Length of exposure
            filename (str, optional): Image is saved to this filename
            dark (bool, optional): Exposure is a dark frame (don't open shutter), default False
            blocking (bool, optional): If False (default) returns immediately after starting
                the exposure, if True will block until it completes.

        Returns:
            threading.Event: Event that will be set when exposure is complete

        """
        assert self.is_connected, self.logger.error("Camera must be connected for take_exposure!")

        assert filename is not None, self.logger.warning("Must pass filename for take_exposure")

        if not self._exposure_event.is_set():
            msg = "Attempt to take exposure on {} while one already in progress.".format(self)
            raise error.PanError(msg)

        # Clear event now to prevent any other exposures starting before this one is finished.
        self._exposure_event.clear()

        # Make sure proxy is in async mode
        Pyro4.asyncproxy(self._proxy, asynchronous=True)

        #Start the exposure
        self.logger.debug(f'Taking {seconds} second exposure on {self.name}: {filename}')

        #Remote method call to start the exposure
        exposure_result = self._proxy.take_exposure(seconds=seconds,
                                                    filename=filename,
                                                    dark=bool(dark),
                                                    *args,
                                                    **kwargs)

        #Start a thread that will set an event once exposure has completed
        exposure_thread = Timer(interval=get_quantity_value(seconds, u.s) + self.readout_time,
                                function=self._async_wait,
                                args=(exposure_result,
                                      'exposure',
                                      self._exposure_event,
                                      self._timeout))
        exposure_thread.start()

        if blocking:
            self._exposure_event.wait()

        return self._exposure_event

    def autofocus(self,
                  seconds=None,
                  focus_range=None,
                  focus_step=None,
                  thumbnail_size=None,
                  keep_files=None,
                  take_dark=None,
                  merit_function='vollath_F4',
                  merit_function_kwargs={},
                  mask_dilations=None,
                  coarse=False,
                  make_plots=False,
                  blocking=False,
                  timeout=None,
                  *args, **kwargs):
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
            timeout (u.second, optional): Total length of time to wait for autofocus sequences
                to complete. If not given will wait indefinitely.

        Returns:
            threading.Event: Event that will be set when autofocusing is complete
        """
        assert self.is_connected, self.logger.error("Camera must be connected for autofocus.")

        if self.focuser is None:
            msg = "Camera must have a focuser for autofocus!"
            self.logger.error(msg)
            raise AttributeError(msg)

        assert self.focuser.is_connected, \
            self.logger.error("Focuser must be connected for autofocus.")

        # Compile aruments into a dictionary
        autofocus_kwargs = {'seconds': seconds,
                            'focus_range': focus_range,
                            'focus_step': focus_step,
                            'keep_files': keep_files,
                            'take_dark': take_dark,
                            'thumbnail_size': thumbnail_size,
                            'merit_function': merit_function,
                            'merit_function_kwargs': merit_function_kwargs,
                            'mask_dilations': mask_dilations,
                            'coarse': coarse,
                            'make_plots': make_plots}
        autofocus_kwargs.update(kwargs)

        # Make sure proxy is in async mode
        Pyro4.asyncproxy(self._proxy, asynchronous=True)

        # Start autofocus
        autofocus_result = {}
        self.logger.debug('Starting autofocus on {}'.format(self.name))
        # Remote method call to start the autofocus
        autofocus_result = self._proxy.autofocus(*args, **autofocus_kwargs)

        # Start a thread that will set an event once autofocus has completed
        autofocus_event = Event()
        autofocus_thread = Thread(target=self._async_wait,
                args=(autofocus_result, 'autofocus', autofocus_event, timeout))
        autofocus_thread.start()

        if blocking:
            autofocus_event.wait()

        return autofocus_event

# Private Methods

    def _start_exposure(self, seconds=None, filename=None, dark=False, header=None):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _readout(self, filename=None):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _async_wait(self, future_result, name='?', event=None, timeout=None):
        # For now not checking for any problems, just wait for everything to return (or timeout)
        if future_result.wait(timeout):
            try:
                result = future_result.value
            except Exception as err:
                # Add some extra text to the exception then re-raise it.
                if len(err.args) >= 1:
                    msg = f"Problem while waiting for {name} on {self.port}: {err.args[0]}"
                    err.args = (msg,) + err.args[1:]
                else:
                    msg = f"Problem while waiting for {name} on {self.port}: {err}"
                self.logger.error(msg)  # Make sure error makes it into the logs
                raise err
            finally:
                if event is not None:
                    event.set()
        else:
            if event is not None:
                event.set()
            msg = "Timeout while waiting for {} on {}".format(name, self.port)
            raise error.Timeout(msg)

        return result


    def _process_fits(self, file_path, info):
        '''
        Override _process_fits, called by process_exposure in take_observation.

        The difference is that we do an NGAS push following the processing.
        '''
        #Call the super method
        result = super()._process_fits(file_path, info)

        #Do the NGAS push
        self._NGASpush(file_path, info)

        return result


    def _NGASpush(self, filename, metadata, filename_ngas=None, port=7778):
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
        #Define the NGAS filename
        if filename_ngas is None:
            extension = os.path.splitext(filename)[-1]
            filename = f"{metadata['image_id']}{extension}"

        #Get the IP address of the NGAS server
        ngas_ip = self.config['ngas_ip']

        #Post the file to the NGAS server
        url = f'http://{ngas_ip}:{port}/QARCHIVE?filename={filename_ngas}&ignore_arcfile=1'
        with open(filename, 'rb') as f:

            self.logger.info(
                    f'Pushing {filename} to NGAS as {filename_ngas}: {url}')

            try:
                #Post the file
                r = requests.post(url, data=f)

                self.logger.debug(f'NGAS response: {r.text}')

                #Confirm success
                r.raise_for_status()

            except Exception as e:
                self.logger.error(f'Error while performing NGAS push: {e}')
                raise(e)

#==============================================================================

@Pyro4.expose
@Pyro4.behavior(instance_mode="single")
class CameraServer(object):
    """
    Wrapper for the camera class for use as a Pyro camera server
    """

    def __init__(self, config_files=None):
        # Pyro classes ideally have no arguments for the constructor. Do it all from config file.
        self.config = load_device_config(config_files=config_files)
        self.host = self.config.get('host')
        self.user = os.getenv('PANUSER', 'huntsman')

        camera_config = self.config.get('camera')
        camera_config.update({'config': self.config})

        module = load_module('pocs.camera.{}'.format(camera_config['model']))
        self._camera = module.Camera(**camera_config)

# Properties

    @property
    def name(self):
        return self._camera.name

    @property
    def model(self):
        return self._camera.model

    @property
    def uid(self):
        return self._camera.uid

    @property
    def readout_time(self):
        return self._camera.readout_time

    @property
    def file_extension(self):
        return self._camera.file_extension

    @property
    def egain(self):
        return self._camera.egain

    @property
    def bit_depth(self):
        return self._camera.bit_depth

    @property
    def temperature(self):
        return self._camera.temperature

    @property
    def target_temperature(self):
        return self._camera.target_temperature

    @target_temperature.setter
    def target_temperature(self, target):
        self._camera.target_temperature = target

    @property
    def temperature_tolerance(self):
        return self._camera.temperature_tolerance

    @temperature_tolerance.setter
    def temperature_tolerance(self, tolerance):
        self._camera.temperature_tolerance = tolerance

    @property
    def cooling_enabled(self):
        return self._camera.cooling_enabled

    @cooling_enabled.setter
    def cooling_enabled(self, enabled):
        self._camera.cooling_enabled = enabled

    @property
    def cooling_power(self):
        return self._camera.cooling_power

    @property
    def filter_type(self):
        return self._camera.filter_type

    @property
    def is_cooled_camera(self):
        return self._camera.is_cooled_camera

    @property
    def is_temperature_stable(self):
        return self._camera.is_temperature_stable

    @property
    def is_exposing(self):
        return self._camera.is_exposing

    @property
    def is_ready(self):
        return self._camera.is_ready

# Methods

    def get_uid(self):
        """
        Added as an alternative to accessing the uid property because that didn't trigger
        object creation.
        """
        return self._camera.uid

    def take_exposure(self, seconds, filename, dark, *args, **kwargs):
        '''
        Parameters
        ----------
        filename (str):
            The filename of the exposure result.

        Returns
        -------
        str:
            The full filename of the exposure output.
        '''
        #Start the exposure and wait for it complete
        self._camera.take_exposure(seconds=seconds,
                                   filename=filename,
                                   dark=dark,
                                   blocking=True,
                                   *args,
                                   **kwargs)

    def autofocus(self, *args, **kwargs):
        if not self.has_focuser:
            msg = "Camera must have a focuser for autofocus!"
            self.logger.error(msg)
            raise AttributeError(msg)
        # Start the autofocus and wait for it to completed
        kwargs['blocking'] = True
        self._camera.focuser.autofocus(*args, **kwargs)

# Focuser methods - these are used by the remote focuser client, huntsman.focuser.pyro.Focuser

    @property
    def has_focuser(self):
        return self._camera.focuser is not None

    @property
    def focuser_name(self):
        return self._camera.focuser.name

    @property
    def focuser_model(self):
        return self._camera.focuser.model

    @property
    def focuser_uid(self):
        return self._camera.focuser.uid

    @property
    def focuser_is_connected(self):
        return self._camera.focuser.is_connected

    @property
    def focuser_position(self):
        return self._camera.focuser.position

    @focuser_position.setter
    def focuser_position(self, position):
        self._camera.focuser.position = position

    @property
    def focuser_min_position(self):
        return self._camera.focuser.min_position

    @property
    def focuser_max_position(self):
        return self._camera.focuser.max_position

    @property
    def focuser_is_moving(self):
        return self._camera.focuser.is_moving

    @property
    def focuser_is_ready(self):
        return self._camera.focuser.is_ready

    @property
    def focuser_autofocus_range(self):
        return self._camera.focuser.autofocus_range

    @focuser_autofocus_range.setter
    def focuser_autofocus_range(self, autofocus_range):
        self._camera.focuser.autofocus_range = autofocus_range

    @property
    def focuser_autofocus_step(self):
        return self._camera.focuser.autofocus_step

    @focuser_autofocus_step.setter
    def focuser_autofocus_step(self, step):
        self._camera.focuser.autofocus_step = step

    @property
    def focuser_autofocus_seconds(self):
        return self._camera.focuser.autofocus_seconds

    @focuser_autofocus_seconds.setter
    def focuser_autofocus_seconds(self, seconds):
        self._camera.focuser.autofocus_seconds = seconds

    @property
    def focuser_autofocus_size(self):
        return self._camera.focuser.autofocus_size

    @focuser_autofocus_size.setter
    def focuser_autofocus_size(self, size):
        self._camera.focuser.autofocus_size = size

    @property
    def focuser_autofocus_keep_files(self):
        return self._camera.focuser.autofocus_keep_files

    @focuser_autofocus_keep_files.setter
    def focuser_autofocus_keep_files(self, keep_files):
        self._camera.focuser.autofocus_keep_files = keep_files

    @property
    def focuser_autofocus_take_dark(self):
        return self._camera.focuser.autofocus_take_dark

    @focuser_autofocus_take_dark.setter
    def focuser_autofocus_take_dark(self, take_dark):
        self._camera.focuser.autofocus_take_dark = take_dark

    @property
    def focuser_autofocus_merit_function(self):
        return self._camera.focuser.autofocus_merit_function

    @focuser_autofocus_merit_function.setter
    def focuser_autofocus_merit_function(self, merit_function):
        self._camera.focuser.autofocus_merit_function = merit_function

    @property
    def focuser_autofocus_merit_function_kwargs(self):
        return self._camera.focuser.autofocus_merit_function_kwargs

    @focuser_autofocus_merit_function_kwargs.setter
    def focuser_autofocus_merit_function_kwargs(self, kwargs):
        self._camera.focuser.autofocus_merit_function_kwargs = kwargs

    @property
    def focuser_autofocus_mask_dilations(self):
        return self._camera.focuser.autofocus_mask_dilations

    @focuser_autofocus_mask_dilations.setter
    def focuser_autofocus_mask_dilations(self, dilations):
        self._camera.focuser.autofocus_mask_dilations = dilations

    def focuser_move_to(self, position):
        return self._camera.focuser.move_to(position)

    def focuser_move_by(self, increment):
        return self._camera.focuser.move_by(increment)
