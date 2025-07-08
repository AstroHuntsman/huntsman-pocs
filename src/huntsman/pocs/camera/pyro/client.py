# fmt: off

import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

import numpy as np
from astropy import units as u
from astropy.io import fits
from huntsman.pocs.camera.camera import AbstractHuntsmanCamera
from huntsman.pocs.filterwheel.pyro import FilterWheel as PyroFilterWheel
from huntsman.pocs.focuser.pyro import Focuser as PyroFocuser
from huntsman.pocs.utils.logger import logger
from huntsman.pocs.utils.pyro import \
    serializers  # Required to set up the custom (de)serializers
from huntsman.pocs.utils.pyro.event import RemoteEvent
from panoptes.utils import error
from panoptes.utils import images as img_utils
from panoptes.utils.images import fits as fits_utils
from panoptes.utils.time import CountdownTimer
from panoptes.utils.utils import get_quantity_value
from Pyro5.api import Proxy


class Camera(AbstractHuntsmanCamera):
    """A python remote object (pyro) camera client.

    This class should be instantiated on the main control computer that is
    running POCS, namely via an `Observatory` object.
    """

    def __init__(self, uri, name='Pyro Camera', model='pyro', port=None, primary=False,
                 config_host=None, config_port=None, *args, **kwargs):
        """
        Args:
            uri (str): The URI of the Pyro proxy camera.
            primary (bool): If this camera is the primary camera for the system, default False.
            model (str): The model of camera, such as 'gphoto2', 'sbig', etc. Default 'simulator'.
            name (str): Name of the camera, default 'Generic Camera'.
            port (str): The port the camera is connected to, typically a usb device, default None.
            config_host (str): The hostname of the config server.
            config_port (int): The port of the config server.
        """
        self.logger = logger

        # We need to replicate init functionality of AbstractCamera without overriding the
        # existing config of the camera proxy.
        self._config_host = config_host or os.getenv('PANOPTES_CONFIG_HOST', 'localhost')
        self._config_port = config_port or os.getenv('PANOPTES_CONFIG_PORT', 6563)
        self.port = port
        self.is_primary = primary
        self.subcomponents = dict()  # Required for "stringifying" the camera

        # The proxy used for communication with the remote instance.
        self._uri = uri
        self.logger.debug(f'Connecting to {port} at {self._uri}')

        # Hardware that may be attached in connect method.
        self.focuser = None
        self.filterwheel = None

        self._exposure_future = None  # Used by self.process_exposure
        self._exposure_executor = ThreadPoolExecutor(max_workers=1)

        # Connect to camera
        self.connect()

    # Properties
    @property
    def _proxy(self):
        return Proxy(self._uri)

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
        """Set or clear the remote exposure event."""
        if is_exposing:
            self._exposure_event.set()
        else:
            self._exposure_event.clear()

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
        self._timeout = self._proxy.get("_timeout")

        # Set up proxies for remote camera's events required by base class
        self._exposure_event = RemoteEvent(self._uri, event_type="camera")
        self._focus_event = RemoteEvent(self._uri, event_type="focuser")

        self._connected = True
        self.logger.debug(f"{self} connected.")

        if self._proxy.has_focuser:
            self.focuser = PyroFocuser(camera=self)

        if self._proxy.has_filterwheel:
            self.filterwheel = PyroFilterWheel(camera=self)

    def take_exposure(self, seconds=1.0 * u.second, filename=None, dark=False, blocking=False,
                      sleep_interval=0.1 * u.second, max_write_time=10, *args, timeout=None,
                      **kwargs):
        """Take an exposure for given number of seconds and saves to provided filename.
        Args:
            seconds (astropy.Quantity, optional): Length of exposure.
            filename (str, optional): Image is saved to this filename.
            dark (bool, optional): Exposure is a dark frame, default False. On cameras that support
                taking dark frames internally (by not opening a mechanical shutter) this will be
                done, for other cameras the light must be blocked by some other means. In either
                case setting dark to True will cause the `IMAGETYP` FITS header keyword to have
                value 'Dark Frame' instead of 'Light Frame'. Set dark to None to disable the
                `IMAGETYP` keyword entirely.
            max_write_time (astropy.Quantity, optional): The maximum allowable delay between the
                file being written on the camaera host and it being fully written on the local
                filesystem. Default 10s.
            sleep_interval (astropy.Quantity, optional): The time to sleep between checks for
                the file existing.
            blocking (bool, optional): If False (default) returns immediately after starting
                the exposure, if True will block (on the client-side) until it completes.
            timeout (float, optional): If provided, override the default timeout with this value.
        Returns:
            concurrent.futures.Future: The Future object for the exposure.
        """
        # Start the exposure
        self.logger.debug(f'Taking {seconds} second exposure on {self}: {filename}')

        # Remote method call to start the exposure
        self._proxy.take_exposure(seconds=seconds, filename=filename, dark=dark, *args, **kwargs)

        # Start the readout thread
        if timeout is None:
            timeout = get_quantity_value(seconds, u.second) + self.readout_time + self._timeout
            timeout += get_quantity_value(max_write_time, u.second)
        else:
            timeout = get_quantity_value(timeout, u.second)

        self._exposure_future = self._exposure_executor.submit(self._wait_for_file, filename,
                                                               timeout)
        if blocking:
            self._exposure_future.result()

        return self._exposure_future

    def take_observation(self, observation, *args, **kwargs):
        """ Overrride class method to add defocusing offset.
        TODO: Move to AbstractCamera.
        """
        focus_offset = 0
        with suppress(AttributeError):
            focus_offset = observation.focus_offset
        return super().take_observation(observation, focus_offset=focus_offset,
                                        *args, **kwargs)

    def autofocus(self, blocking=False, timeout=None, coarse=False, *args, **kwargs):
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
            blocking (bool, optional): Whether to block (on the client-side) until autofocus
                complete, default False.
            timeout (float, optional): The client-side autofocus timeout. The default value of
                `None` will lookup the `focusing.<focus_type>.timeout` value in the config server.
                 If not provided, a default fallback of 600 seconds is used.

        Returns:
            threading.Event: Event that will be set when autofocusing is complete

        Raises:
            ValueError: If invalid values are passed for any of the focus parameters.
        """
        if self.focuser is None:
            msg = "Camera must have a focuser for autofocus!"
            self.logger.error(msg)
            raise AttributeError(msg)

        if timeout is None:
            coarse_str = "coarse" if coarse else "fine"
            timeout = self.get_config(f"focusing.{coarse_str}.timeout", default=600)

        # Remote method call to start the exposure
        self.logger.debug(f'Starting autofocus on {self} with timeout: {timeout}.')
        self._proxy.autofocus(blocking=False, coarse=coarse, *args, **kwargs)
        if blocking:
            self._proxy.event_wait("focuser", timeout=timeout)

        return self._focus_event

    def process_exposure(self, *args, **kwargs):
        """ Small wrapper around `Camera.process_exposure` that makes sure the image is actually
        written before starting processing. """
        self._exposure_future.result()
        return super().process_exposure(*args, **kwargs)
     
    def process_video_files(self,
                         metadata,
                         observation_event,
                         max_frames,
                         compress_fits=None,
                         record_observations=None,
                         make_pretty_images=None):
        """ Processes the exposure.

        Performs the following steps:

            1. First checks to make sure that the file exists on the file system.
            2. Calls `_process_fits` with the filename and info, which is specific to each camera.
            3. Makes pretty images if requested.
            4. Records observation metadata if requested.
            5. Compresses FITS files if requested.
            6. Sets the observation_event.

        If the camera is a primary camera, extract the jpeg image and save metadata to database
        `current` collection. Saves metadata to `observations` collection for all images.

        Args:
            metadata (dict): Header metadata saved for the image
            observation_event (threading.Event): An event that is set signifying that the
                camera is done with this exposure
            compress_fits (bool or None): If FITS files should be fpacked into .fits.fz.
                If None (default), checks the `observations.compress_fits` config-server key.
            record_observations (bool or None): If observation metadata should be saved.
                If None (default), checks the `observations.record_observations`
                config-server key.
            make_pretty_images (bool or None): If should make a jpg from raw image.
                If None (default), checks the `observations.make_pretty_images`
                config-server key.

        Raises:
            FileNotFoundError: If the FITS file isn't at the specified location.
        """
        # Wait for exposure to complete. Timeout handled by exposure thread.
        while self.is_exposing:
            time.sleep(1)

        self.logger.debug(f'Starting exposure processing for {observation_event}')

        if compress_fits is None:
            compress_fits = self.get_config('observations.compress_fits', default=False)

        if make_pretty_images is None:
            make_pretty_images = self.get_config('observations.make_pretty_images', default=False)

        image_id = metadata['image_id']
        seq_id = metadata['sequence_id']
        files_dir = metadata['files_dir']
        exptime = metadata['exptime']
        field_name = metadata['field_name']

        # Get list of files and limit to max_frames
        files = sorted(glob.glob(files_dir + '/*.fits'))
        num_files = len(files)
        
        # Define number of worker threads
        num_workers = 5  # Using 5 threads as specified
        
        for file_path in files:
            # Make sure image exists.
            if not os.path.exists(file_path):
                observation_event.set()
                raise FileNotFoundError(
                    f"Expected image at {file_path=!r} does not exist or " +
                    "cannot be accessed, cannot process.")

            self.logger.debug(f'Starting FITS processing for {file_path}')
            
            file_path = super()._process_fits(file_path, metadata)
            
            self.logger.debug(f'Finished FITS processing for {file_path}')

            # TODO make this async and take it out of camera.
            if make_pretty_images:
                try:
                    image_title = f'{field_name} [{exptime}s] {seq_id}'

                    self.logger.debug(f"Making pretty image for file_path={file_path!r}")
                    link_path = None
                    if metadata['is_primary']:
                        # This should be in the config somewhere.
                        link_path = os.path.expandvars('$PANDIR/images/latest.jpg')

                    img_utils.make_pretty_image(file_path,
                                                title=image_title,
                                                link_path=link_path)
                except Exception as e:  # pragma: no cover
                    self.logger.warning(f'Problem with extracting pretty image: {e!r}')
                    
            if compress_fits:
                self.logger.debug(f'Compressing file_path={file_path!r}')
                compressed_file_path = fits_utils.fpack(file_path)
                self.logger.debug(f'Compressed {compressed_file_path}')
            

        metadata['exptime'] = get_quantity_value(metadata['exptime'], unit='second')

        if record_observations:
            self.logger.debug(f"Adding current observation to db: {image_id}")
            self.db.insert_current('observations', metadata)

        # Mark the event as done
        observation_event.set()

    def process_concurrent_video_files(self, metadata, observation_event, max_frames,
                                     compress_fits=None, record_observations=None,
                                     make_pretty_images=None):
        """Process video files using multiple threads.
        Each thread processes a distinct subset of files.
        """
        
        # Wait for exposure to complete
        while self.is_exposing:
            time.sleep(1)

        self.logger.debug(f'Starting exposure processing for {observation_event}')

        if compress_fits is None:
            compress_fits = self.get_config('observations.compress_fits', default=False)
        if make_pretty_images is None:
            make_pretty_images = self.get_config('observations.make_pretty_images', default=False)

        files_dir = metadata['files_dir']
        
        # Get list of files and limit to max_frames
        files = sorted(glob.glob(files_dir + '/*.fits'))[:max_frames]
        num_files = len(files)
        
        self.logger.info(f"Found {num_files} files to process in {files_dir}")
        
        # Define number of worker threads
        num_workers = 5
        
        # Calculate files per thread
        files_per_thread = int(np.ceil(num_files / num_workers))
        self.logger.info(f"Using {num_workers} threads, {files_per_thread} files per thread")
        
        def process_file_chunk(chunk_id, file_list):
            """Process a chunk of files assigned to a single thread"""
            self.logger.info(f"Thread {chunk_id}: Starting processing of {len(file_list)} files")
            processed_files = []
            
            # import pdb
            # pdb.set_trace()
            
            for i, file_path in enumerate(file_list):
                try:
                    self.logger.info(f"Thread {chunk_id}: Processing file {i+1}/{len(file_list)}: {file_path}")
                    
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(
                            f"Expected image at {file_path=!r} does not exist or cannot be accessed")

                    processed_path = self._process_fits(file_path, metadata)
                    self.logger.debug(f"Thread {chunk_id}: Completed FITS processing for {processed_path}")

                    if make_pretty_images:
                        try:
                            image_title = f'{metadata["field_name"]} [{metadata["exptime"]}s] {metadata["sequence_id"]}'
                            link_path = None
                            if metadata['is_primary']:
                                link_path = os.path.expandvars('$PANDIR/images/latest.jpg')

                            img_utils.make_pretty_image(processed_path,
                                                      title=image_title,
                                                      link_path=link_path)
                            self.logger.debug(f"Thread {chunk_id}: Created pretty image for {processed_path}")
                        except Exception as e:
                            self.logger.warning(f"Thread {chunk_id}: Problem with extracting pretty image: {e!r}")

                    if compress_fits:
                        self.logger.debug(f"Thread {chunk_id}: Compressing {processed_path}")
                        compressed_path = fits_utils.fpack(processed_path)
                        self.logger.debug(f"Thread {chunk_id}: Compressed to {compressed_path}")
                    
                    processed_files.append(processed_path)
                    
                except Exception as e:
                    self.logger.error(f"Thread {chunk_id}: Error processing file {file_path}: {e}")
                    
            self.logger.info(f"Thread {chunk_id}: Completed processing all files")
            return processed_files

        # Split files into chunks for each thread
        file_chunks = [files[i:i + files_per_thread] 
                      for i in range(0, len(files), files_per_thread)]
        
        self.logger.info(f"Divided files into {len(file_chunks)} chunks")
        
        # Process chunks in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            try:
                # Submit all chunks for processing
                self.logger.info("Submitting chunks to thread pool")
                futures = [executor.submit(process_file_chunk, i, chunk) 
                          for i, chunk in enumerate(file_chunks)]
                
                # Wait for all tasks to complete and collect results
                all_processed_files = []
                self.logger.info("Waiting for all threads to complete")
                
                for i, future in enumerate(futures):
                    try:
                        processed_files = future.result()
                        self.logger.info(f"Thread {i} completed successfully, processed {len(processed_files)} files")
                        all_processed_files.extend(processed_files)
                    except Exception as e:
                        self.logger.error(f"Thread {i} failed with error: {e}")

            except Exception as e:
                self.logger.error(f"Error in parallel processing: {e}")
        
        self.logger.info(f"All threads completed. Total processed files: {len(all_processed_files)}")

        metadata['exptime'] = get_quantity_value(metadata['exptime'], unit='second')

        if record_observations:
            self.logger.debug(f"Adding current observation to db: {metadata['image_id']}")
            self.db.insert_current('observations', metadata)

        # Mark the event as done
        observation_event.set()
        self.logger.info("Processing complete, observation event set")

    # Private Methods
    def _wait_for_file(self, filename, timeout, sleep_interval=0.1):
        """ Wait for the file to be written.
        Useful when files are written from camera to host over network with SSHFS, which can be
        slow.
        Args:
            filename (str): The filename to wait for.
            timeout (float): The timeout in seconds.
            sleep_interval (float, optional): Wait for this long in between checks. Default 0.1s.
        """
        sleep_interval = get_quantity_value(sleep_interval, u.second)
        proxy = self._proxy
        timer = CountdownTimer(timeout)

        self.logger.debug(f'Waiting for {filename} to exist with timeout of {timeout}s.')

        while not timer.expired():

            # Make sure the file exists and we can read it
            if not proxy.is_reading_out and os.path.exists(filename):
                try:
                    fits.open(filename, output_verify='exception')
                    self.logger.debug(f"Finished waiting for file {filename}.")
                    return
                except Exception as e:
                    self.logger.error(f'Problem reading out file: {e!r}')

            time.sleep(sleep_interval)

        raise error.Timeout(f"{timeout!r} reached for {filename=} to exist on {self}.")


    # Private Methods
    def _wait_for_video_files(self, foldername, timeout, max_frames, sleep_interval=0.1):
        """ Wait for the file to be written.
        Useful when files are written from camera to host over network with SSHFS, which can be
        slow.
        Args:
            filename (str): The filename to wait for.
            timeout (float): The timeout in seconds.
            sleep_interval (float, optional): Wait for this long in between checks. Default 0.1s.
        """
        sleep_interval = get_quantity_value(sleep_interval, u.second)
        proxy = self._proxy
        timer = CountdownTimer(timeout)

        self.logger.debug(f'Waiting for {foldername} to exist with timeout of {timeout}s.')

        while not timer.expired():

            # Make sure the file exists and we can read it
            if not proxy.is_reading_out and os.path.exists(foldername):
            
                try:
                    files = glob.glob(foldername + '/*.fits')
                    if len(files) == max_frames:
                        fits.open(files[0], output_verify='exception')
                        self.logger.debug(f"Finished waiting for file {foldername}.")
                        return
                    else:
                        self.logger.debug(f"Waiting for {max_frames-len(files)} more frames.")
                except Exception as e:
                    self.logger.error(f'Problem reading out file: {e!r}')

            time.sleep(sleep_interval)

        raise error.Timeout(f"{timeout!r} reached for {foldername=} to exist on {self}.")

    def _wait_for_concurrent_video_files(self, foldername, timeout, max_frames, sleep_interval=0.1):
        """Wait for video files with better completion checking."""
        sleep_interval = get_quantity_value(sleep_interval, u.second)
        proxy = self._proxy
        timer = CountdownTimer(timeout)

        self.logger.debug(f'Waiting for {foldername} to exist with timeout of {timeout}s.')

        while not timer.expired():
            # First check if camera is still processing
            if proxy.is_reading_out:
                time.sleep(sleep_interval)
                continue

            # Then check if folder exists and has all files
            if os.path.exists(foldername):
                try:
                    files = glob.glob(foldername + '/*.fits')
                    num_files = len(files)
                    
                    if num_files == max_frames:
                        # Verify first and last file are readable
                        fits.open(files[0], output_verify='exception')
                        fits.open(files[-1], output_verify='exception')
                        self.logger.debug(f"All {max_frames} files written and verified.")
                        return
                    elif num_files < max_frames:
                        if not proxy.is_reading_out:
                            self.logger.warning(f"Camera finished but only {num_files}/{max_frames} "
                                            f"files found.")
                    else:
                        self.logger.warning(f"Found {num_files} files, expected {max_frames}")
                        
                except Exception as e:
                    self.logger.error(f'Problem verifying files: {e!r}')

            time.sleep(sleep_interval)

        raise error.Timeout(f"Timeout waiting for {max_frames} files in {foldername}")

    def _start_exposure(self, **kwargs):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _readout(self, **kwargs):
        """Dummy method on the client required to overwrite @abstractmethod"""
        pass

    def _set_cooling_enabled(self):
        """Dummy method required by the abstract class"""
        raise NotImplementedError

    def _set_target_temperature(self):
        """Dummy method required by the abstract class"""
        raise NotImplementedError


    def take_video(self, seconds=1.0 * u.second, max_frames=None, 
        frame_rate=None,
        duration=None,
        chunking_enabled=False,
        dark=False, blocking=False, files_dir=None,
        sleep_interval=0.1 * u.second, max_write_time=10, *args, timeout=None,
        **kwargs):
        """Take an exposure for given number of seconds and saves to provided filename.
        Args:
            seconds (astropy.Quantity, optional): Length of exposure.
            filename (str, optional): Image is saved to this filename.
            dark (bool, optional): Exposure is a dark frame, default False. On cameras that support
                taking dark frames internally (by not opening a mechanical shutter) this will be
                done, for other cameras the light must be blocked by some other means. In either
                case setting dark to True will cause the `IMAGETYP` FITS header keyword to have
                value 'Dark Frame' instead of 'Light Frame'. Set dark to None to disable the
                `IMAGETYP` keyword entirely.
            max_write_time (astropy.Quantity, optional): The maximum allowable delay between the
                file being written on the camaera host and it being fully written on the local
                filesystem. Default 10s.
            sleep_interval (astropy.Quantity, optional): The time to sleep between checks for
                the file existing.
            blocking (bool, optional): If False (default) returns immediately after starting
                the exposure, if True will block (on the client-side) until it completes.
            timeout (float, optional): If provided, override the default timeout with this value.
        Returns:
            concurrent.futures.Future: The Future object for the exposure.
        """
        
        # Start the exposure
        self.logger.debug(f'Taking {seconds} second exposure on {self}: {files_dir}')

        # breakpoint()
        
        # Remote method call to start the exposure
        self._proxy.take_video(seconds=seconds, 
            max_frames=max_frames, 
            frame_rate=frame_rate, 
            duration=duration,
            dark=dark, 
            files_dir=files_dir, 
            chunking_enabled=chunking_enabled, 
            *args, **kwargs)
    
        # breakpoint()

        # Start the readout thread
        if timeout is None:
            timeout = get_quantity_value(seconds, u.second)*max_frames + self.readout_time + self._timeout
            timeout += get_quantity_value(max_write_time, u.second)
        else:
            timeout = get_quantity_value(timeout, u.second)

        # reading out file
        # self._exposure_future = self._exposure_executor.submit(self._wait_for_video_files, files_dir,
        #                                                        timeout, max_frames)
        
        self._exposure_future = self._exposure_executor.submit(self._wait_for_concurrent_video_files, files_dir,
                                                               timeout, max_frames)

        
        if blocking:
            self._exposure_future.result()

        return self._exposure_future

    def process_nats_video_files(self, metadata, observation_event, max_frames,
                                     compress_fits=None, record_observations=None,
                                     make_pretty_images=None):
        """Process video files using multiple threads.
        Each thread processes a distinct subset of files.
        """
        
        # Wait for exposure to complete
        while self.is_exposing:
            time.sleep(1)

        self.logger.debug(f'Starting exposure processing for {observation_event}')

        metadata['exptime'] = get_quantity_value(metadata['exptime'], unit='second')

        if record_observations:
            self.logger.debug(f"Adding current observation to db: {metadata['image_id']}")
            self.db.insert_current('observations', metadata)

        # Mark the event as done
        observation_event.set()
        self.logger.info("Processing complete, observation event set")
