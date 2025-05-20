# fmt: off

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from queue import Empty, Queue

import numpy as np
from astropy import units as u
from astropy.time import Time
from huntsman.pocs.camera.camera import AbstractHuntsmanCamera
from huntsman.pocs.camera.libasi import HuntsmanASIDriver
from panoptes.pocs.camera.libasi import ASIDriver
from panoptes.pocs.camera.sdk import AbstractSDKCamera
from panoptes.utils import error
from panoptes.utils.images import fits as fits_utils
from panoptes.utils.utils import get_quantity_value
from usb.core import find as finddev

import nats
import os
import asyncio
import json

# from minio import Minio
# from minio.threadpool import ThreadPool
# from huntsman.pocs.camera.utils import write_minio_fits

class Camera(AbstractSDKCamera, AbstractHuntsmanCamera):
    _driver = None  # Class variable to store the ASI driver interface
    _cameras = []  # Cache of camera string IDs
    _assigned_cameras = set()  # Camera string IDs already in use.
    _usb_vendor_id = 0x03c3  # Fixed for ZWO cameras

    def __init__(self,
                 name='ZWO ASI Camera',
                 gain=None,
                 image_type=None,
                 *args, **kwargs):
        """
        ZWO ASI Camera class
        Args:
            serial_number (str): camera serial number or user set ID (up to 8 bytes). See notes.
            gain (int, optional): gain setting, using camera's internal units. If not given
                the camera will use its current or default setting.
            image_type (str, optional): image format to use (one of 'RAW8', 'RAW16', 'RGB24'
                or 'Y8'). Default is to use 'RAW16' if supported by the camera, otherwise
                the camera's own default will be used.
            *args, **kwargs: additional arguments to be passed to the parent classes.
        Notes:
            ZWO ASI cameras don't have a 'port', they only have a non-deterministic integer
            camera_ID and, probably, an 8 byte serial number. Optionally they also have an
            8 byte ID that can be written to the camera firmware by the user (using ASICap,
            or pocs.camera.libasi.ASIDriver.set_ID()). The camera should be identified by
            its serial number or, if it doesn't have one, by the user set ID.
        """
        kwargs['readout_time'] = kwargs.get('readout_time', 0.1)
        kwargs['timeout'] = kwargs.get('timeout', 5)
        # ZWO cameras cannot take internal darks (not even supported in the API yet).
        kwargs['internal_darks'] = kwargs.get('internal_darks', False)

        self._video_event = threading.Event()

        self._gain = gain
        
        # Define subjects based on producer ID
        producer_id=0
        self.memory_subject = f"camera.memory.{producer_id}.frame"
        self.disk_subject = f"camera.archive.{producer_id}.frame"
        self.NATS_SERVER = os.environ.get("NATS_SERVER", "nats://192.168.80.100:4222")
        
        self.nats_client = None
    
        # self.nats_client = self._setup_nats()

        if image_type:
            self._image_type = image_type
        # Take monochrome 12 bit raw images by default, if we can
        else:
            self._image_type = 'RAW16'

        super().__init__(name, HuntsmanASIDriver, *args, **kwargs)

        # Increase default temperature_tolerance for ZWO cameras because the
        # default value is too low for their temperature resolution.
        self.temperature_tolerance = kwargs.get('temperature_tolerance', 0.6 * u.Celsius)

        self.logger.info(f'Initialised {self}.')

        self._current_focus_offset = 0

    def __del__(self):
        """ Attempt some clean up """
        with suppress(AttributeError):
            self.shutdown_chunk_publisher()
            camera_ID = self._handle
            Camera._driver.close_camera(camera_ID)
            self.logger.debug("Closed ZWO camera {}".format(camera_ID))
        super().__del__()

    # Properties

    @property
    def image_type(self):
        """ Current camera image type, one of 'RAW8', 'RAW16', 'Y8', 'RGB24' """
        roi_format = Camera._driver.get_roi_format(self._handle)
        return roi_format['image_type']

    @image_type.setter
    def image_type(self, new_image_type):
        if new_image_type not in self.properties['supported_video_format']:
            msg = "Image type '{} not supported by {}".format(new_image_type, self.model)
            self.logger.error(msg)
            raise ValueError(msg)
        roi_format = self._driver.get_roi_format(self._handle)
        roi_format['image_type'] = new_image_type
        Camera._driver.set_roi_format(self._handle, **roi_format)

    @property
    def bit_depth(self):
        """ADC bit depth"""
        return self.properties['bit_depth']

    @property
    def temperature(self):
        """ Current temperature of the camera's image sensor """
        return self._control_getter('TEMPERATURE')[0]

    @AbstractSDKCamera.target_temperature.getter
    def target_temperature(self):
        """ Current value of the target temperature for the camera's image sensor cooling control.
        Can be set by assigning an astropy.units.Quantity
        """
        return self._control_getter('TARGET_TEMP')[0]

    @AbstractSDKCamera.cooling_enabled.getter
    def cooling_enabled(self):
        """ Current status of the camera's image sensor cooling system (enabled/disabled) """
        return self._control_getter('COOLER_ON')[0]

    @property
    def cooling_power(self):
        """ Current power level of the camera's image sensor cooling system (as a percentage). """
        return self._control_getter('COOLER_POWER_PERC')[0]

    @property
    def gain(self):
        """ Current value of the camera's gain setting in internal units.
        See `egain` for the corresponding electrons / ADU value.
        """
        return self._control_getter('GAIN')[0]

    @gain.setter
    def gain(self, gain):
        self._control_setter('GAIN', gain)
        self._refresh_info()  # This will update egain value in self.properties

    @property
    def egain(self):
        """ Image sensor gain in e-/ADU for the current gain, as reported by the camera."""
        return self.properties['e_per_adu']

    @property
    def is_exposing(self):
        """ True if an exposure is currently under way, otherwise False """
        return Camera._driver.get_exposure_status(self._handle) == "WORKING"

    # Methods
    async def _setup_nats_async(self):
        """Set up the NATS connection asynchronously - exactly like in producer_nopub.py"""
        try:
            # Connect to NATS
            nc = await nats.connect(servers=[self.NATS_SERVER])
            js = nc.jetstream()
            
            self.logger.info(f"Connected to NATS server at {self.NATS_SERVER}")
            return (nc, js)
        except Exception as e:
            self.logger.error(f"Failed to connect to NATS: {e}")
            return None

    async def _publish_to_nats_async(self, subject, data, headers):
        """Publish data to NATS subject - exactly like in producer_nopub.py"""
        try:
            if self.nats_client is None:
                connection = await self._setup_nats_async()
                if connection is None:
                    return False
                self.nc, self.nats_client = connection

            # This matches exactly with producer_nopub.py's await js.publish()
            await self.nats_client.publish(subject, data, headers=headers)
            return True
        except Exception as e:
            self.logger.error(f"Error publishing to NATS: {e}")
            self.nats_client = None
            return False

    def _publish_frame_to_nats(self, frame_data, headers):
        """
        Synchronous wrapper for the async publish function.
        Creates and manages its own event loop.
        """
        # Ensure we have an event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No event loop exists yet
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async publish function in this loop
        try:
            return loop.run_until_complete(
                self._publish_to_nats_async(self.memory_subject, frame_data, headers)
            )
        except Exception as e:
            self.logger.error(f"Failed to publish frame to NATS: {e}")
            return False
   
    def connect(self):
        """
        Connect to ZWO ASI camera.
        Gets 'camera_ID' (needed for all driver commands), camera properties and details
        of available camera commands/parameters.
        """
        self.logger.debug("Connecting to {}".format(self))
        self._refresh_info()
        self._handle = self.properties['camera_ID']
        self.model, _, _ = self.properties['name'].partition('(')
        if self.properties['has_cooler']:
            self._is_cooled_camera = True
        if self.properties['is_color_camera']:
            self._filter_type = self.properties['bayer_pattern']
        else:
            self._filter_type = 'M'  # Monochrome
        Camera._driver.open_camera(self._handle)
        Camera._driver.init_camera(self._handle)
        self._control_info = Camera._driver.get_control_caps(self._handle)
        self._info['control_info'] = self._control_info  # control info accessible via properties
        Camera._driver.disable_dark_subtract(self._handle)

        if self._gain is not None:
            self.gain = self._gain
        self.image_type = self._image_type

        self._connected = True

    def reconnect(self):
        """ Reconnect to the camera. """
        Camera._driver.close_camera(self._handle)
        self._reset_usb()
        self.connect()
        self.cooling_enabled = True

    def take_exposure(self, *args, **kwargs):
        """ Overrride class method to add defocusing offset.
        Note that the focus offset is checked at the exposure level so that we don't end up
        moving the focuser back and forth unnecessarily.
        TODO: Move to AbstractCamera.
        Args:
            defocused (bool, optional): If True, apply the defocusing offset before the exposure.
                Default: False.
            *args, **kwargs: Parsed to super().take_exposure.
        Returns:
            threading.Thread: The readout thread, which joins when readout has finished.
        """
        focus_offset = kwargs.pop("focus_offset", 0)
        required_focus_move = focus_offset - self._current_focus_offset

        if required_focus_move != 0:
            self.logger.debug(f"Setting focus offset for {self} to: {focus_offset}.")

            default_pos = self.focuser.position - self._current_focus_offset

            new_pos = self.focuser.move_by(required_focus_move)

            # The actual offset may be different from the one we expected
            actual_offset = new_pos - default_pos

            # Update the current focus offset
            self._current_focus_offset = actual_offset

        return super().take_exposure(*args, **kwargs)
    
    

    def take_video(self, *args, **kwargs):
        """ Overrride class method to add defocusing offset.
        Note that the focus offset is checked at the exposure level so that we don't end up
        moving the focuser back and forth unnecessarily.
        TODO: Move to AbstractCamera.
        Args:
            defocused (bool, optional): If True, apply the defocusing offset before the exposure.
                Default: False.
            *args, **kwargs: Parsed to super().take_exposure.
        Returns:
            threading.Thread: The readout thread, which joins when readout has finished.
        """
        focus_offset = kwargs.pop("focus_offset", 0)
        required_focus_move = focus_offset - self._current_focus_offset

        if required_focus_move != 0:
            self.logger.debug(f"Setting focus offset for {self} to: {focus_offset}.")

            default_pos = self.focuser.position - self._current_focus_offset

            new_pos = self.focuser.move_by(required_focus_move)

            # The actual offset may be different from the one we expected
            actual_offset = new_pos - default_pos

            # Update the current focus offset
            self._current_focus_offset = actual_offset
        
        # video_obj = super().take_exposure(*args, **kwargs)
        
        breakpoint()
        
        filename_root = kwargs['files_dir']
        max_frames = kwargs['max_frames']
        seconds = kwargs['seconds']
        
        video_obj = self.start_video(seconds, filename_root, max_frames)
        # video_obj = self.start_concurrent_video(seconds, filename_root, max_frames)

        return video_obj



    def start_video(self, seconds, filename_root, max_frames, image_type=None):
    
        if not isinstance(seconds, u.Quantity):
            seconds = seconds * u.second
        self._control_setter('EXPOSURE', seconds)
        if image_type:
            self.image_type = image_type

        roi_format = Camera._driver.get_roi_format(self._handle)
        width = int(get_quantity_value(roi_format['width'], unit=u.pixel))
        height = int(get_quantity_value(roi_format['height'], unit=u.pixel))
        image_type = roi_format['image_type']

        timeout = 2 * seconds + self._timeout * u.second

        video_args = (width,
                      height,
                      image_type,
                      timeout,
                      filename_root,
                      self.file_extension,
                      int(max_frames),
                      self._create_fits_header(seconds, dark=False))
        video_thread = threading.Thread(target=self._video_readout,
                                        args=video_args,
                                        daemon=True)

        Camera._driver.start_video_capture(self._handle)
        self._video_event.clear()
        video_thread.start()
        self.logger.debug("Video capture started on {}".format(self))
        
        return video_thread
    
            
    def start_concurrent_video(self, seconds, filename_root, max_frames, image_type=None):
        """Start video capture with concurrent frame processing.
        
        Args:
            seconds (u.Quantity): Exposure time for each frame
            filename_root (str): Root name for saved files
            max_frames (int): Maximum number of frames to capture
            image_type (str, optional): Image format to use. If None, uses current camera setting.
        
        Returns:
            threading.Thread: The video processing thread that manages capture and writing
        
        Notes:
            - The function starts a main video thread that manages both reading and writing threads
            - Frame reading is done in a single thread to maintain sequential capture
            - Frame writing is done with multiple threads for I/O optimization
            - Progress can be monitored through the logger
            - Use stop_video() to terminate capture before max_frames
        """
        
        breakpoint()
                
        import psutil
        import os
        import threading
        
        # Get main thread's current core
        main_process = psutil.Process()
        main_thread_id = threading.get_ident()
        main_thread = next(thread for thread in main_process.threads() 
                        if thread.id == main_thread_id)
        main_core = main_thread.cpu_num()

        self.logger.info(f"Main thread running on core {main_core}")
        
        # Dynamic core allocation based on main thread location
        available_cores = list(range(4))  # Assuming 4 cores
        available_cores.remove(main_core)  # Remove main thread's core

        # Allocate remaining cores
        SYSTEM_CORE = main_core  # Main thread & system services
        READER_CORE = available_cores[0]  # First available core for reader
        WRITER_CORES = available_cores[1:]  # Remaining cores for writers
        NUM_WRITER_THREADS = len(WRITER_CORES)
    
        self.logger.info(f"""Core allocation:
            System/Main: Core {SYSTEM_CORE}
            Reader: Core {READER_CORE}
            Writers: Cores {WRITER_CORES}
        """)
       
        breakpoint() 
        
        # Ensure seconds is a Quantity
        if not isinstance(seconds, u.Quantity):
            seconds = seconds * u.second
            
        # Set exposure time
        self._control_setter('EXPOSURE', seconds)
        
        # Set image type if specified
        if image_type:
            self.image_type = image_type

        # Get ROI format for frame size
        roi_format = Camera._driver.get_roi_format(self._handle)
        width = int(get_quantity_value(roi_format['width'], unit=u.pixel))
        height = int(get_quantity_value(roi_format['height'], unit=u.pixel))
        image_type = roi_format['image_type']

        # Calculate timeout based on exposure time
        # timeout = 2 * seconds + self._timeout * u.second
        
        # Calculate timeout based on exposure time (convert to seconds)
        base_timeout = 2 * seconds.to(u.second).value + self._timeout
        if isinstance(base_timeout, u.Quantity):
            timeout = base_timeout.to(u.second).value
        else:
            timeout = float(base_timeout)
        
        # Prepare arguments for video processing
        video_args = (width,
                    height,
                    image_type,
                    timeout,
                    filename_root,
                    self.file_extension,
                    int(max_frames),
                    self._create_fits_header(seconds, dark=False))

        # Start video capture on camera
        try:
            Camera._driver.start_video_capture(self._handle)
            self._video_event.clear()
        except Exception as e:
            self.logger.error(f"Failed to start video capture: {e}")
            raise
        
        breakpoint()
        # Create and start video processing thread
        video_thread = threading.Thread(
            target=self._multithread_video_readout,
            args=video_args,
            name=f"Video-{filename_root}",
            daemon=True
        )
        
        breakpoint()

        try:
            video_thread.start()
            #self._concurrent_video_readout(*video_args)
            self.logger.info(f"Started video capture on {self}:")
            self.logger.info(f"- Exposure: {get_quantity_value(seconds, u.second):.3f}s")
            self.logger.info(f"- Frames: {max_frames}")
            self.logger.info(f"- Size: {width}x{height}")
            self.logger.info(f"- Type: {image_type}")
            self.logger.info(f"- Output: {filename_root}_NNNNNN.{self.file_extension}")
        except Exception as e:
            self.logger.error(f"Failed to start video processing thread: {e}")
            self.stop_concurrent_video()  # Cleanup camera if thread start fails
            raise

        return video_thread

    def stop_concurrent_video(self):
        """Stop video capture and cleanup resources.
        
        This method:
        1. Sets the video event to signal stopping
        2. Stops camera video capture
        3. Allows threads to cleanup gracefully
        """
        self._video_event.set()
        Camera._driver.stop_video_capture(self._handle)
        self.logger.debug("Video capture stopped on {}".format(self))
        
        # try:
        #     Camera._driver.stop_video_capture(self._handle)
        #     self.logger.info(f"Stopped video capture on {self}")
        # except Exception as e:
        #     self.logger.error(f"Error stopping video capture: {e}")


    def stop_video(self):
        self._video_event.set()
        Camera._driver.stop_video_capture(self._handle)
        self.logger.debug("Video capture stopped on {}".format(self))

    # Private methods

    def _set_target_temperature(self, target):
        self._control_setter('TARGET_TEMP', target)
        self._target_temperature = target

    def _set_cooling_enabled(self, enable):
        self._control_setter('COOLER_ON', enable)

    def _video_readout(self,
                       width,
                       height,
                       image_type,
                       timeout,
                       filename_root,
                       file_extension,
                       max_frames,
                       header):

        start_time = time.monotonic()
        good_frames = 0
        bad_frames = 0

        # Set up chunk publisher system if not already done
        if not hasattr(self, 'chunk_queue'):
            self.setup_chunk_publisher()

        # Calculate number of bits that have been used to pad the raw data to RAW16 format.
        if self.image_type == 'RAW16':
            pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
        else:
            pad_bits = 0

        for frame_number in range(max_frames):
            if self._video_event.is_set():
                break
            # This call will block for up to timeout milliseconds waiting for a frame
            video_data = Camera._driver.get_video_data(self._handle,
                                                      width,
                                                      height,
                                                      image_type,
                                                      timeout)
            if video_data is not None:
                now = Time.now()
                header.set('DATE-OBS', now.fits, 'End of exposure + readout')
                filename = "{}_{:06d}.{}".format(filename_root, frame_number, file_extension)
                # Fix 'raw' data scaling by changing from zero padding of LSBs
                # to zero padding of MSBs.
                video_data = np.right_shift(video_data, pad_bits)
                
                self.logger.info(f"Processing frame {frame_number}, shape: {video_data.shape}")
                
                # Prepare base headers
                header_dict = dict(header)
                base_headers = {
                    'frame_number': str(frame_number),
                    'original_width': str(width),
                    'original_height': str(height),
                    'header': json.dumps(header_dict)
                }
                
                # Divide frame into chunks
                chunks = self.divide_image_into_chunks(video_data)
                
                # Add all chunks to queue
                for chunk_data, chunk_coords, chunk_indices in chunks:
                    self.chunk_queue.put((
                        chunk_data,
                        base_headers,
                        chunk_coords,
                        chunk_indices
                    ))
                
                # Wait for all chunks to be processed before moving to next frame
                self.chunk_queue.join()
                self.logger.info(f"Frame {frame_number}: All {len(chunks)} chunks processed")
                
                good_frames += 1
                
            else:
                bad_frames += 1
                
            elapsed_time = (time.monotonic() - start_time) * u.second
            
            n=1
            FRAME_SIZE_MB = 40.0
            mbps = (good_frames * FRAME_SIZE_MB/n) /(time.monotonic() - start_time)
            
            self.logger.info("Captured {} of {} frames in {:.2f} ({:.2f} fps), {} frames lost, Throughput: {:.2f} MB/s".format(
                good_frames,
                max_frames,
                elapsed_time,
                get_quantity_value(good_frames / elapsed_time),
                bad_frames,
                mbps))

        if frame_number == max_frames - 1:
            # No one called stop_video() before max_frames so have to call it here
            self.stop_video()

        elapsed_time = (time.monotonic() - start_time) * u.second
        self.logger.info("Captured {} of {} frames in {:.2f} ({:.2f} fps), {} frames lost".format(
            good_frames,
            max_frames,
            elapsed_time,
            get_quantity_value(good_frames / elapsed_time),
            bad_frames))
        
    def _start_exposure(self, seconds, filename, dark, header, *args, **kwargs):
        self._control_setter('EXPOSURE', seconds)
        roi_format = Camera._driver.get_roi_format(self._handle)
        Camera._driver.start_exposure(self._handle)
        readout_args = (filename,
                        roi_format['width'],
                        roi_format['height'],
                        header)
        return readout_args

    def _readout(self, filename, width, height, header):
        exposure_status = Camera._driver.get_exposure_status(self._handle)
        if exposure_status == 'SUCCESS':
            try:
                image_data = Camera._driver.get_exposure_data(self._handle,
                                                              width,
                                                              height,
                                                              self.image_type)
            except RuntimeError as err:
                raise error.PanError('Error getting image data from {}: {}'.format(self, err))
            else:
                # Fix 'raw' data scaling by changing from zero padding of LSBs
                # to zero padding of MSBs.
                if self.image_type == 'RAW16':
                    pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
                    image_data = np.right_shift(image_data, pad_bits)

                fits_utils.write_fits(data=image_data,
                                      header=header,
                                      filename=filename)
        elif exposure_status == 'FAILED':

            # Reconnect to the camera so it can still be used
            self.logger.warning(f"Exposure failed on {self}. Reconnecting camera.")
            self.reconnect()

            raise error.PanError(f"Exposure failed on {self}")

        elif exposure_status == 'IDLE':
            raise error.PanError("Exposure missing on {}".format(self))
        else:
            raise error.PanError("Unexpected exposure status on {}: '{}'".format(
                self, exposure_status))

    def _create_fits_header(self, seconds, dark):
        header = super()._create_fits_header(seconds, dark)
        header.set('CAM-GAIN', self.gain, 'Internal units')
        header.set('XPIXSZ', get_quantity_value(self.properties['pixel_size'], u.um), 'Microns')
        header.set('YPIXSZ', get_quantity_value(self.properties['pixel_size'], u.um), 'Microns')
        return header

    def _refresh_info(self):
        self._info = Camera._driver.get_camera_property(self._address)

    def _control_getter(self, control_type):
        if control_type in self._control_info:
            return Camera._driver.get_control_value(self._handle, control_type)
        else:
            raise error.NotSupported("{} has no '{}' parameter".format(self.model, control_type))

    def _control_setter(self, control_type, value):
        if control_type not in self._control_info:
            raise error.NotSupported("{} has no '{}' parameter".format(self.model, control_type))

        control_name = self._control_info[control_type]['name']
        if not self._control_info[control_type]['is_writable']:
            raise error.NotSupported("{} cannot set {} parameter'".format(
                self.model, control_name))

        if value != 'AUTO':
            # Check limits.
            max_value = self._control_info[control_type]['max_value']
            if value > max_value:
                self.logger.warning(f"Cannot set {control_name} to {value}, clipping to max value:"
                                    f" {max_value}.")
                Camera._driver.set_control_value(self._handle, control_type, max_value)
                return

            min_value = self._control_info[control_type]['min_value']
            if value < min_value:
                self.logger.warning(f"Cannot set {control_name} to {value}, clipping to min value:"
                                    f" {min_value}.")
                Camera._driver.set_control_value(self._handle, control_type, min_value)
                return
        else:
            if not self._control_info[control_type]['is_auto_supported']:
                msg = "{} cannot set {} to AUTO".format(self.model, control_name)
                raise error.IllegalValue(msg)

        Camera._driver.set_control_value(self._handle, control_type, value)

    def _reset_usb(self):
        """ Reset the USB device. """
        self.logger.warning(f"Resetting USB for {self}.")
        for product_id in Camera._driver.get_product_ids():
            dev = finddev(idVendor=self._usb_vendor_id, idProduct=product_id)
            if dev:
                self.logger.debug(f"Identified USB product ID: {product_id}.")
                break
        if not dev:
            raise RuntimeError(f"Unable to determine USB product ID for {self}.")
        dev.reset()


    def _concurrent_video_readout(self,
                    width,
                    height,
                    image_type,
                    timeout,
                    filename_root,
                    file_extension,
                    max_frames,
                    header):
        """Video readout with optimized I/O threading and proper cleanup.
        
        Args:
            width (int): Image width in pixels
            height (int): Image height in pixels
            image_type (str): Type of image data
            timeout (float): Timeout duration in seconds
            filename_root (str): Base filename for saving frames
            file_extension (str): File extension for saved frames
            max_frames (int): Maximum number of frames to capture
            header (fits.Header): FITS header template for saved frames
        """
        breakpoint()
        
        start_time = time.monotonic()
        
        # Convert timeout to seconds if it's a Quantity
        if isinstance(timeout, u.Quantity):
            timeout = timeout.to(u.second).value
        
        # Configure thread pool for I/O bound operations
        frame_rate = getattr(self, 'frame_rate', 50)  # default to 50 if not set
        num_writer_threads = min(20, max(2, int(frame_rate / 2)))  # 1 thread per 5 fps, capped at 20
        queue_size = min(50, max(30, int(frame_rate / 2)))  # Dynamic queue size based on frame rate
        
        self.logger.info(f"Starting video capture:")
        self.logger.info(f"- Frame rate: {frame_rate} fps")
        self.logger.info(f"- Writer threads: {num_writer_threads}")
        self.logger.info(f"- Queue size: {queue_size}")
        self.logger.info(f"- Max frames: {max_frames}")
        
        data_queue = Queue(maxsize=queue_size)
        stop_event = threading.Event()
        completion_event = threading.Event()
        
        breakpoint()
        
        # # Calculate bit padding
        # if self.image_type == 'RAW16':
        #     pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
        # else:
        #     pad_bits = 0

        def write_frame_data(frame_number, video_data):
            """Writer thread function to save frame to disk"""
            
            # import pdb
            # pdb.set_trace()
            
            try:
                thread_id = threading.current_thread().name
                write_start = time.monotonic()
                
                # Create a copy of the header for this frame
                frame_header = header.copy()
                now = Time.now()
                frame_header.set('DATE-OBS', now.fits, 'End of exposure + readout')
                
                # Process data if needed
                # if pad_bits:
                #     video_data = np.right_shift(video_data, pad_bits)
                
                # Construct filename and save
                filename = f"{filename_root}/{frame_number:06d}.{file_extension}"
                fits_utils.write_fits(video_data, frame_header, filename)
                
                write_time = time.monotonic() - write_start
                if frame_number % 50 == 0:
                    self.logger.debug(f"Thread {thread_id}: Frame {frame_number} "
                                    f"written in {write_time:.3f}s")
                return True
                
            except Exception as e:
                self.logger.error(f"Thread {thread_id}: Error writing frame {frame_number}: {e}")
                return False

        def read_video_data():
            """Reader thread function to get data from camera"""
            from datetime import datetime, timezone

            # import pdb
            # pdb.set_trace()
            
            try:
                frames_read = 0
                read_start_time = time.monotonic()
                
                self.logger.info("Reader thread started")
                
                start_datetime = datetime.now(timezone.utc)
                start_time = time.perf_counter()
                frame_start_datetime = start_datetime
                frame_start_time = start_time
    
                
                while frames_read < max_frames and not stop_event.is_set():
                    try:
                        # Add backpressure if queue is nearly full
                        if self._video_event.is_set():
                            break
            
                        if data_queue.qsize() >= data_queue.maxsize - 2:
                            time.sleep(0.005)
                            continue
                        
                        video_data = Camera._driver.get_video_data(self._handle,
                                                                width,
                                                                height,
                                                                image_type,
                                                                timeout)
                        
                        frame_got_data_time = time.perf_counter()
                        frame_end_datetime = datetime.now(timezone.utc) 
                    
                        
                                                                
                        if video_data is not None:
                            frames_read += 1
                            data_queue.put((frames_read, video_data))
                            
                            if frames_read % 50 == 0:
                                elapsed = time.monotonic() - read_start_time
                                current_fps = frames_read / elapsed
                                self.logger.info(f"Reader status: {frames_read}/{max_frames} frames "
                                            f"({current_fps:.1f} fps)")
                        else:
                            self.logger.warning("Failed to get video data")
                            
                    except Exception as e:
                        self.logger.error(f"Error reading video data: {e}")
                        stop_event.set()
                        break
                        
                self.logger.info(f"Reader thread completed: {frames_read}/{max_frames} frames read")
                
            finally:
                # Signal no more data
                data_queue.put(None)

        
        
        # Start reader thread
        reader_thread = threading.Thread(target=read_video_data)
        
        breakpoint()
        
        reader_thread.start()

        # Process frames with ThreadPoolExecutor
        good_frames = 0
        bad_frames = 0
        
        breakpoint()
        
        try:
            with ThreadPoolExecutor(max_workers=num_writer_threads) as executor:
                futures = []
                active_futures = set()
                
                while not stop_event.is_set():
                    try:
                        # Clean up completed futures
                        active_futures = {f for f in active_futures if not f.done()}
                        
                        # Log status periodically
                        if len(futures) % 100 == 0 and futures:
                            self.logger.info(f"Writer pool status: "
                                        f"Active: {len(active_futures)}, "
                                        f"Queue: {data_queue.qsize()}, "
                                        f"Total: {len(futures)}")
                        
                        # Get next frame from queue
                        queue_item = data_queue.get(timeout=timeout)
                        
                        breakpoint()
                        
                        if queue_item is None:  # End signal
                            break
                            
                        frame_number, frame_data = queue_item
                        
                        breakpoint()
                        future = executor.submit(write_frame_data, frame_number, frame_data)
                        futures.append(future)
                        
                        breakpoint()
                        active_futures.add(future)
                        
                    except Exception as e:
                        self.logger.error(f"Error in main processing loop: {e}")
                        stop_event.set()
                        break

                # Wait for all writing tasks to complete
                for future in futures:
                    try:
                        if future.result(timeout=timeout):
                            good_frames += 1
                        else:
                            bad_frames += 1
                    except Exception as e:
                        self.logger.error(f"Error waiting for future: {e}")
                        bad_frames += 1
                        
        finally:
            # Cleanup
            stop_event.set()
            reader_thread.join(timeout=5)
            
            # Clear the queue with timeout
            try:
                while True:
                    data_queue.get_nowait()  # Remove remaining items
            except Empty:
                # Queue is empty now
                pass
                
            # Signal completion
            completion_event.set()
            
            # Log final statistics
            elapsed_time = time.monotonic() - start_time
            fps = good_frames / elapsed_time
            
            self.logger.info("Video capture complete:")
            self.logger.info(f"- Total frames: {good_frames + bad_frames}")
            self.logger.info(f"- Successful frames: {good_frames}")
            self.logger.info(f"- Failed frames: {bad_frames}")
            self.logger.info(f"- Time elapsed: {elapsed_time:.2f}s")
            self.logger.info(f"- Average frame rate: {fps:.1f} fps")
            self.stop_video()

        # if self._video_event.is_set():
        #     self.stop_video()

        return completion_event



    def _multithread_video_readout(self,
                        width,
                        height,
                        image_type,
                        timeout,
                        filename_root,
                        file_extension,
                        max_frames,
                        header):
        """Video readout with reader/writer threads on separate cores.
        
        Uses:
        - One dedicated reader thread pinned to a core
        - Multiple writer threads on separate core(s)
        - Shared queue for thread communication
        """
        import os
        import psutil
        from queue import Queue
        from datetime import datetime, timezone
        
        breakpoint()
        
        start_time = time.monotonic()

        # Configure queue size based on frame rate
        frame_rate = getattr(self, 'frame_rate', 50)
        queue_size = min(100, max(20, int(frame_rate)))  # Buffer ~1-2 seconds worth of frames
        data_queue = Queue(maxsize=queue_size)
        
        # Configure number of writer threads
        num_writer_threads = min(20, max(2, int(frame_rate / 5)))
        
        stop_event = threading.Event()
        completion_event = threading.Event()

        def pin_to_core(core_id):
            """Pin current thread to specified CPU core"""
            process = psutil.Process()
            try:
                process.cpu_affinity([core_id])
                self.logger.debug(f"Pinned thread to core {core_id}")
            except Exception as e:
                self.logger.warning(f"Failed to pin to core {core_id}: {e}")

        def read_video_data():
            """Reader thread function - runs on dedicated core"""
            try:
                # Pin reader thread to last core
                available_cores = psutil.cpu_count()
                pin_to_core(available_cores - 1)
                
                frames_read = 0
                read_start_time = time.monotonic()
                
                self.logger.info("Reader thread started")
                
                while frames_read < max_frames and not stop_event.is_set():
                    try:
                        if self._video_event.is_set():
                            break
                            
                        # Add backpressure if queue is nearly full
                        if data_queue.qsize() >= data_queue.maxsize - 2:
                            time.sleep(0.001)  # Short sleep
                            continue
                        
                        # Get frame from camera
                        video_data = Camera._driver.get_video_data(self._handle,
                                                                width,
                                                                height,
                                                                image_type,
                                                                timeout)
                                                                
                        if video_data is not None:
                            frames_read += 1
                            frame_time = datetime.now(timezone.utc)
                            
                            # Put frame data and metadata in queue
                            data_queue.put({
                                'frame_number': frames_read,
                                'data': video_data,
                                'timestamp': frame_time
                            })
                            
                            if frames_read % 10 == 0:
                                elapsed = time.monotonic() - read_start_time
                                current_fps = frames_read / elapsed
                                self.logger.info(f"Reader status: {frames_read}/{max_frames} frames "
                                            f"({current_fps:.1f} fps)")
                        else:
                            self.logger.warning("Failed to get video data")
                            
                    except Exception as e:
                        self.logger.error(f"Error reading frame: {e}")
                        
                self.logger.info(f"Reader completed: {frames_read}/{max_frames} frames")
                
            except Exception as e:
                self.logger.error(f"Fatal error in reader thread: {e}")
            finally:
                # Signal no more frames
                data_queue.put(None)

        def write_frame_data(frame_info):
            """Writer thread function to save frame to disk"""
            try:
                # Get frame info
                frame_number = frame_info['frame_number']
                video_data = frame_info['data']
                frame_time = frame_info['timestamp']
                
                # Create frame-specific header
                frame_header = header.copy()
                frame_header.set('DATE-OBS', frame_time.isoformat(), 'Frame timestamp')
                
                # Process data if needed (bit shifting etc)
                if self.image_type == 'RAW16':
                    pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
                    video_data = np.right_shift(video_data, pad_bits)
                
                # Save frame
                filename = f"{filename_root}/{frame_number:06d}.{file_extension}"
                fits_utils.write_fits(video_data, frame_header, filename)
                
                if frame_number % 10 == 0:
                    self.logger.debug(f"Wrote frame {frame_number}")
                    
                return True
                
            except Exception as e:
                self.logger.error(f"Error writing frame {frame_number}: {e}")
                return False
        
        # Start reader thread on dedicated core
        reader_thread = threading.Thread(target=read_video_data, name="VideoReader")
        reader_thread.start()

        # Start writer threads on remaining cores
        writer_cores = list(range(psutil.cpu_count() - 1))  # All cores except last
        good_frames = 0
        bad_frames = 0
        
        try:
            with ThreadPoolExecutor(max_workers=num_writer_threads) as executor:
                futures = []
                
                while not stop_event.is_set():
                    try:
                        # Get next frame from queue
                        frame_info = data_queue.get(timeout=timeout)
                        
                        if frame_info is None:  # Reader finished
                            break
                            
                        # Submit frame for writing
                        future = executor.submit(write_frame_data, frame_info)
                        futures.append(future)
                        
                    except Empty:
                        if not reader_thread.is_alive():
                            break
                        continue
                        
                # Wait for remaining writes to complete
                for future in futures:
                    try:
                        if future.result(timeout=timeout):
                            good_frames += 1
                        else:
                            bad_frames += 1
                    except Exception as e:
                        self.logger.error(f"Error in future: {e}")
                        bad_frames += 1
                        
        except Exception as e:
            self.logger.error(f"Error in writer pool: {e}")
        finally:
            # Cleanup
            stop_event.set()
            reader_thread.join(timeout=5)
            
            # Log final statistics
            elapsed_time = time.monotonic() - start_time
            fps = good_frames / elapsed_time if elapsed_time > 0 else 0
            
            self.logger.info("Video capture complete:")
            self.logger.info(f"- Successful frames: {good_frames}")
            self.logger.info(f"- Failed frames: {bad_frames}")
            self.logger.info(f"- Time elapsed: {elapsed_time:.2f}s")
            self.logger.info(f"- Average frame rate: {fps:.1f} fps")
            
            completion_event.set()

        return completion_event
    
        
    def _multicore_video_readout(self,
                        width,
                        height,
                        image_type,
                        timeout,
                        filename_root,
                        file_extension,
                        max_frames,
                        header):
        """Video readout optimized for 4-core server with other Pyro services.
        
        Core allocation strategy:
        - Core 0: Reserved for system & Pyro services (I/O bound management)
        - Core 1: Shared between reader thread and services
        - Cores 2-3: Writer thread pool
        """
        breakpoint()
        
        import os
        import psutil
        from queue import Queue
        from datetime import datetime, timezone

        start_time = time.monotonic()
        
        # Conservative core allocation
        SYSTEM_CORE = 0      # Reserved for system & Pyro services
        READER_CORE = 1      # Shared core for reader
        WRITER_CORES = [2, 3]  # Dedicated cores for writers
        NUM_WRITER_THREADS = len(WRITER_CORES)
        
        # Smaller queue size to reduce memory pressure
        frame_rate = getattr(self, 'frame_rate', 50)
        queue_size = min(100, max(20, int(frame_rate)))  # Buffer ~1 second
        data_queue = Queue(maxsize=queue_size)
        
        stop_event = threading.Event()
        completion_event = threading.Event()

        def pin_to_core(core_id):
            """Pin thread to specified CPU core with nice value"""
            try:
                # Set core affinity
                os.sched_setaffinity(0, {core_id})
                
                # Set nice value (lower = higher priority)
                # Reader: higher priority (-10)
                # Writers: normal priority (0)
                if core_id == READER_CORE:
                    os.nice(-10)  # Higher priority for reader
                else:
                    os.nice(0)    # Normal priority for writers
                    
                self.logger.debug(f"Pinned thread to core {core_id}")
            except Exception as e:
                self.logger.warning(f"Failed to pin to core {core_id}: {e}")

        def read_video_data():
            """Reader thread function with adaptive sleep"""
            try:
                # Pin reader to shared core with high priority
                pin_to_core(READER_CORE)
                self.logger.info(f"Reader thread started on core {READER_CORE}")
                
                frames_read = 0
                read_start_time = time.monotonic()
                last_log_time = read_start_time
                
                # Adaptive sleep parameters
                min_sleep = 0.0001  # 100 microseconds
                max_sleep = 0.001   # 1 millisecond
                current_sleep = min_sleep
                
                while frames_read < max_frames and not stop_event.is_set():
                    try:
                        if self._video_event.is_set():
                            break
                            
                        # Adaptive backpressure based on queue fullness
                        queue_fullness = data_queue.qsize() / queue_size
                        if queue_fullness > 0.8:  # Queue more than 80% full
                            current_sleep = min(max_sleep, current_sleep * 1.5)
                            time.sleep(current_sleep)
                            continue
                        else:
                            current_sleep = max(min_sleep, current_sleep * 0.8)
                        
                        # Get frame from camera
                        video_data = Camera._driver.get_video_data(self._handle,
                                                                width,
                                                                height,
                                                                image_type,
                                                                timeout)
                                                                
                        if video_data is not None:
                            frames_read += 1
                            frame_time = datetime.now(timezone.utc)
                            
                            data_queue.put({
                                'frame_number': frames_read,
                                'data': video_data,
                                'timestamp': frame_time
                            })
                            
                            # Log progress every 2 seconds
                            current_time = time.monotonic()
                            if current_time - last_log_time >= 2.0:
                                elapsed = current_time - read_start_time
                                current_fps = frames_read / elapsed
                                self.logger.debug(
                                    f"Reader: {frames_read}/{max_frames} frames "
                                    f"({current_fps:.1f} fps, queue: {data_queue.qsize()}, "
                                    f"sleep: {current_sleep*1000:.2f}ms)"
                                )
                                last_log_time = current_time
                                
                            if frames_read % 10 == 0:
                                elapsed = time.monotonic() - read_start_time
                                current_fps = frames_read / elapsed
                                self.logger.info(f"Reader status: {frames_read}/{max_frames} frames "
                                            f"({current_fps:.1f} fps)")
                                
                        else:
                            self.logger.warning("Failed to get video data")
                            time.sleep(min_sleep)
                            
                    except Exception as e:
                        self.logger.error(f"Error reading frame: {e}")
                        time.sleep(min_sleep)
                        
                self.logger.info(f"Reader completed: {frames_read}/{max_frames} frames")
                
            except Exception as e:
                self.logger.error(f"Fatal error in reader thread: {e}")
            finally:
                data_queue.put(None)

        def write_frame_data(frame_info):
            """Writer thread function with I/O optimization"""
            try:
                frame_number = frame_info['frame_number']
                video_data = frame_info['data']
                frame_time = frame_info['timestamp']
                
                # Prepare header (CPU work)
                frame_header = header.copy()
                frame_header.set('DATE-OBS', frame_time.isoformat(), 'Frame timestamp')
                
                if self.image_type == 'RAW16':
                    pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
                    video_data = np.right_shift(video_data, pad_bits)
                
                # Write file (I/O work)
                filename = f"{filename_root}/{frame_number:06d}.{file_extension}"
                fits_utils.write_fits(video_data, frame_header, filename)
                
                return True
                
            except Exception as e:
                self.logger.error(f"Error writing frame {frame_number}: {e}")
                return False

        # Start reader thread
        reader_thread = threading.Thread(target=read_video_data, name="VideoReader")
        reader_thread.start()

        good_frames = 0
        bad_frames = 0
        last_log_time = time.monotonic()
        
        try:
            with ThreadPoolExecutor(max_workers=NUM_WRITER_THREADS) as executor:
                # Pin writer threads to dedicated cores
                for core_id in WRITER_CORES:
                    pin_to_core(core_id)
                    
                futures = []
                active_futures = set()
                
                while not stop_event.is_set():
                    try:
                        # Clean up completed futures
                        active_futures = {f for f in active_futures if not f.done()}
                        
                        frame_info = data_queue.get(timeout=timeout)
                        if frame_info is None:
                            break
                            
                        future = executor.submit(write_frame_data, frame_info)
                        futures.append(future)
                        active_futures.add(future)
                        
                        # Log progress every 2 seconds
                        current_time = time.monotonic()
                        if current_time - last_log_time >= 2.0:
                            completed = len([f for f in futures if f.done()])
                            pending = len(active_futures)
                            self.logger.debug(
                                f"Writers: {completed} written, {pending} pending, "
                                f"queue: {data_queue.qsize()}"
                            )
                            last_log_time = current_time
                        
                    except Empty:
                        if not reader_thread.is_alive():
                            break
                        continue
                        
                # Wait for remaining writes
                for future in futures:
                    try:
                        if future.result(timeout=timeout):
                            good_frames += 1
                        else:
                            bad_frames += 1
                    except Exception as e:
                        self.logger.error(f"Error in future: {e}")
                        bad_frames += 1
                        
        except Exception as e:
            self.logger.error(f"Error in writer pool: {e}")
        finally:
            stop_event.set()
            reader_thread.join(timeout=5)
            
            elapsed_time = time.monotonic() - start_time
            fps = good_frames / elapsed_time if elapsed_time > 0 else 0
            
            self.logger.info("Video capture complete:")
            self.logger.info(f"- Successful frames: {good_frames}")
            self.logger.info(f"- Failed frames: {bad_frames}")
            self.logger.info(f"- Time elapsed: {elapsed_time:.2f}s")
            self.logger.info(f"- Average frame rate: {fps:.1f} fps")
            
            completion_event.set()

        return completion_event

    def divide_image_into_chunks(self, image_data, n_chunks_x=8, n_chunks_y=8):
        """
        Divides an image into a grid of chunks.
        
        Args:
            image_data (numpy.ndarray): 2D image array to divide
            n_chunks_x (int): Number of chunks in x direction (width)
            n_chunks_y (int): Number of chunks in y direction (height)
            
        Returns:
            list: List of tuples, each containing:
                - chunk data (numpy.ndarray)
                - coordinates (x_start, y_start, x_end, y_end)
                - chunk indices (chunk_x, chunk_y)
        """
        height, width = image_data.shape
        
        # Calculate chunk dimensions
        chunk_width = width // n_chunks_x
        chunk_height = height // n_chunks_y
        
        chunks = []
        
        for y in range(n_chunks_y):
            for x in range(n_chunks_x):
                # Calculate chunk boundaries
                x_start = x * chunk_width
                y_start = y * chunk_height
                
                # Adjust width/height for edge chunks
                if x == n_chunks_x - 1:
                    x_end = width
                else:
                    x_end = x_start + chunk_width
                    
                if y == n_chunks_y - 1:
                    y_end = height
                else:
                    y_end = y_start + chunk_height
                
                # Extract the chunk
                chunk = image_data[y_start:y_end, x_start:x_end]
                
                # Store chunk with its coordinates and indices
                chunks.append((
                    chunk,
                    (x_start, y_start, x_end, y_end),
                    (x, y)
                ))
        
        return chunks

    def create_chunk_headers(self, base_headers, chunk_coords, chunk_indices, n_chunks_x=8, n_chunks_y=8):
        """
        Create headers for a specific chunk based on the original frame headers.
        
        Args:
            base_headers (dict): Original headers from the full frame
            chunk_coords (tuple): Coordinates (x_start, y_start, x_end, y_end)
            chunk_indices (tuple): Grid position (x, y)
            n_chunks_x (int): Number of chunks in x direction
            n_chunks_y (int): Number of chunks in y direction
            
        Returns:
            dict: Headers for the chunk
        """
        x, y = chunk_indices
        x_start, y_start, x_end, y_end = chunk_coords
        
        # Create a copy of base headers
        chunk_headers = base_headers.copy()
        
        # Add chunk-specific information
        chunk_headers.update({
            'chunk_x': str(x),
            'chunk_y': str(y),
            'x_start': str(x_start),
            'y_start': str(y_start),
            'x_end': str(x_end),
            'y_end': str(y_end),
            'width': str(x_end - x_start),
            'height': str(y_end - y_start),
            'total_chunks_x': str(n_chunks_x),
            'total_chunks_y': str(n_chunks_y),
            'chunk_number': str(y * n_chunks_x + x)
        })
        
        return chunk_headers

    def setup_chunk_publisher(self):
        """Set up the multi-threaded chunk publisher system with shared thread-local NATS connections."""
        import queue
        import threading
        
        # Create queue with max size of 64 chunks (one full frame)
        self.chunk_queue = queue.Queue(maxsize=64)
        self.chunk_stop_event = threading.Event()
        self.chunk_workers = []
        
        # Thread-local storage for NATS connections
        self.thread_local = threading.local()
        
        # Create 8 worker threads
        for i in range(8):
            worker = threading.Thread(
                target=self._chunk_publisher_worker,
                name=f"ChunkPublisher-{i}",
                daemon=True
            )
            worker.start()
            self.chunk_workers.append(worker)
        
        self.logger.info("Started 8 chunk publisher threads")

    def _ensure_nats_connection(self):
        """Ensure this thread has a NATS connection."""
        if not hasattr(self.thread_local, 'nats_nc') or not self.thread_local.nats_nc.is_connected:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Connect to NATS
            self.thread_local.loop = loop
            self.thread_local.nats_nc = loop.run_until_complete(nats.connect(servers=[self.NATS_SERVER]))
            self.thread_local.nats_js = self.thread_local.nats_nc.jetstream()
            
            self.logger.info(f"Thread {threading.current_thread().name} connected to NATS")
        
        return self.thread_local.nats_nc, self.thread_local.nats_js, self.thread_local.loop

    def _publish_frame_to_nats_thread_local(self, data, headers):
        """Publish data to NATS using thread-local connection."""
        try:
            # Ensure we have a connection for this thread
            nc, js, loop = self._ensure_nats_connection()
            
            # Create coroutine to publish the data
            async def publish():
                await js.publish(self.memory_subject, data, headers=headers)
                return True
            
            # Run the publish coroutine
            return loop.run_until_complete(publish())
            
        except Exception as e:
            self.logger.error(f"Error publishing to NATS: {e}")
            # For timeout errors, try to reset connection
            if "timeout" in str(e).lower():
                if hasattr(self.thread_local, 'nats_nc'):
                    delattr(self.thread_local, 'nats_nc')
            return False

    def _chunk_publisher_worker(self):
        """Worker thread to publish chunks from queue using thread-local NATS connection."""
        while not self.chunk_stop_event.is_set():
            try:
                # Get chunk from queue with timeout
                chunk_item = self.chunk_queue.get(timeout=0.5)
                if chunk_item is None:
                    # None is signal to exit
                    self.chunk_queue.task_done()
                    break
                
                # Unpack chunk data
                chunk_data, base_headers, chunk_coords, chunk_indices = chunk_item
                
                # Create headers for this chunk
                chunk_headers = self.create_chunk_headers(
                    base_headers, 
                    chunk_coords, 
                    chunk_indices
                )
                
                # Publish the chunk using thread-local connection
                success = self._publish_frame_to_nats_thread_local(chunk_data.tobytes(), headers=chunk_headers)
                
                # Mark task as done
                self.chunk_queue.task_done()
                
            except Empty:  # Make sure this is imported: from queue import Empty
                # Queue timeout, continue checking
                continue
            except Exception as e:
                self.logger.error(f"Error in chunk publisher: {e}")
                # Mark task as done even on error
                try:
                    self.chunk_queue.task_done()
                except:
                    pass

    def shutdown_chunk_publisher(self):
        """Safely shut down chunk publisher system."""
        if hasattr(self, 'chunk_stop_event'):
            self.chunk_stop_event.set()
            
            # Send None to each worker to signal exit
            for _ in range(len(self.chunk_workers)):
                try:
                    self.chunk_queue.put(None, timeout=0.5)
                except:
                    pass
                
            # Wait for workers to exit
            for worker in self.chunk_workers:
                worker.join(timeout=2)
            
            # Close NATS connections for each thread if possible
            for thread in self.chunk_workers:
                try:
                    if hasattr(thread, '_thread_local') and hasattr(thread._thread_local, 'nats_nc'):
                        nc = thread._thread_local.nats_nc
                        loop = thread._thread_local.loop
                        if nc.is_connected:
                            loop.run_until_complete(nc.close())
                except Exception as e:
                    self.logger.error(f"Error closing thread NATS connection: {e}")
            
            self.logger.info("Chunk publisher system shut down")


