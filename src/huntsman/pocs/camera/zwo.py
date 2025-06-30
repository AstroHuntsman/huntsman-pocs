# fmt: off

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from queue import Empty, Queue

import nats
import numpy as np
from astropy import units as u
from astropy.time import Time
from huntsman.pocs.camera.camera import AbstractHuntsmanCamera
from huntsman.pocs.camera.libasi import HuntsmanASIDriver
from huntsman.pocs.utils.config import get_own_ip
from panoptes.pocs.camera.libasi import ASIDriver
from panoptes.pocs.camera.sdk import AbstractSDKCamera
from panoptes.utils import error
from panoptes.utils.images import fits as fits_utils
from panoptes.utils.utils import get_quantity_value
from usb.core import find as finddev

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
        producer_id = self._get_producer_id()
        
        self.memory_subject = f"camera.memory.{producer_id}.frame"
        self.disk_subject = f"camera.archive.{producer_id}.frame"
        self.NATS_SERVER = os.environ.get("NATS_SERVER", "nats://192.168.80.100:4222")
        self.chunking_enabled = False
        
        # last memory check and memory usage
        self.memory_usage = 0.0
        self.MEMORY_THRESHOLD = 50.0
        self.last_memory_check = time.time()
        self.MEMORY_STATUS_FILE = os.environ.get("MEMORY_STATUS_FILE", "/huntsman/images/memory_status.json")
        if os.path.exists(self.MEMORY_STATUS_FILE):
            with open(self.MEMORY_STATUS_FILE, 'r') as f:
                memory_data = json.load(f)
                self.memory_usage = memory_data.get('memory_used_percent', 0.0)
                self.MEMORY_THRESHOLD = memory_data.get('threshold', 50.0)
                
        print(f"Memory usage: {self.memory_usage}%")
        print(f"MEMORY_THRESHOLD: {self.MEMORY_THRESHOLD}%")
        
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
            if self.chunking_enabled:
                self.shutdown_chunk_publisher()
            else :
                self.shutdown_single_publisher()
                
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
    
    def check_memory_usage(self):
        current_time = time.time()

        # Only check every 2 seconds
        if current_time - self.last_memory_check < 2.0:
            return self.memory_usage

        try:
            if os.path.exists(self.MEMORY_STATUS_FILE):
                with open(self.MEMORY_STATUS_FILE, 'r') as f:
                    memory_data = json.load(f)
                    self.memory_usage = memory_data.get('memory_used_percent', 0)
        except Exception as e:
            print(f"Error reading memory status: {e}")

        self.last_memory_check = current_time

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
        """Publish data to NATS subject with acknowledgment"""
        try:
            if self.nats_client is None:
                connection = await self._setup_nats_async()
                if connection is None:
                    return False
                self.nc, self.nats_client = connection

            # Wait for acknowledgment from JetStream
            ack = await self.nats_client.publish(subject, data, headers=headers)
            
            # Verify the message was stored
            if ack and ack.seq:
                self.logger.debug(f"Message stored with sequence: {ack.seq}")
                return True
            else:
                self.logger.error("No acknowledgment received from JetStream")
                return False
            
        except Exception as e:
            self.logger.error(f"Error publishing to NATS: {e}")
            self.nats_client = None
            return False

    def _publish_frame_to_nats(self, frame_data, headers):
        """
        Synchronous wrapper for the async publish function with proper loop management.
        """
        # Always create a fresh event loop for each publish operation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Reset any existing connections since we're using a new loop
        self.nats_client = None
        if hasattr(self, 'nc'):
            self.nc = None
    
        try:
            self.check_memory_usage()
            if self.memory_usage < self.MEMORY_THRESHOLD:
                success = loop.run_until_complete(
                    self._publish_to_nats_async(self.memory_subject, frame_data, headers)
                )
            else:
                success = loop.run_until_complete(
                    self._publish_to_nats_async(self.disk_subject, frame_data, headers)
                )
            return success
        except Exception as e:
            self.logger.error(f"Failed to publish frame to NATS: {e}")
            return False
        finally:
            # Close connections on the same loop they were created on
            try:
                if hasattr(self, 'nc') and self.nc and not self.nc.is_closed:
                    loop.run_until_complete(self.nc.close())
            except Exception as e:
                self.logger.warning(f"Error closing NATS connection: {e}")
            finally:
                # Always close the loop and reset state
                loop.close()
                self.nats_client = None
                if hasattr(self, 'nc'):
                    self.nc = None
            
    def _get_producer_id(self):
        """Get producer ID from camera ID or IP address last digit.
        
        Returns:
            int: Producer ID (0-9) for NATS subjects
        """
        try:
            # Fall back to extracting from IP address
            ip_address = get_own_ip()
            last_digit = int(ip_address.split('.')[-1]) % 10
            
            print(f"Using camera_ID {last_digit} as producer_id on server: {ip_address}")
            return last_digit
            
        except Exception as e:
            print(f"Could not determine producer_id from IP: {e}")
        
        # Final fallback to default
        
        return 0
  
   
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
        
        # breakpoint()
        
        filename_root = kwargs['files_dir']
        max_frames = kwargs['max_frames']
        frame_rate = kwargs['frame_rate']
        duration = kwargs['duration']
        seconds = kwargs['seconds']
        self.chunking_enabled = kwargs.get('chunking_enabled', False)
        
        video_obj = self.start_video(seconds, filename_root, max_frames, frame_rate, duration)

        return video_obj



    def start_video(self, seconds, filename_root, max_frames, frame_rate, duration, image_type=None):
    
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
                      frame_rate,
                      duration,
                      self._create_fits_header(seconds, dark=False))
        video_thread = threading.Thread(target=self._video_readout,
                                        args=video_args,
                                        daemon=True)

        Camera._driver.start_video_capture(self._handle)
        self._video_event.clear()
        video_thread.start()
        self.logger.debug("Video capture started on {}".format(self))
        
        return video_thread

    def stop_video(self):
        self._video_event.set()
        Camera._driver.stop_video_capture(self._handle)
        
        # Clean up based on chunking mode
        # if self.chunking_enabled:
        #     if hasattr(self, 'chunk_workers') and self.chunk_workers:
        #         self.shutdown_chunk_publisher()
        if self.chunking_enabled==False:
            # Clean up single publisher system
            self.shutdown_single_publisher()
        
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
                       frame_rate,
                       duration,
                       header):

        start_time = time.monotonic()
        duration_seconds = get_quantity_value(duration, u.second)
        good_frames = 0
        bad_frames = 0

        # Set up chunk publisher system if not already done
        if self.chunking_enabled:
            if not hasattr(self, 'chunk_queue'):
                self.setup_chunk_publisher()

        # Calculate number of bits that have been used to pad the raw data to RAW16 format.
        if self.image_type == 'RAW16':
            pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
        else:
            pad_bits = 0

        # for frame_number in range(max_frames):
        frame_number = 0
        while True:
            if time.monotonic() - start_time > duration_seconds:
                break
            
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
            
                if self.chunking_enabled:
                    # Divide frame into chunks
                    
                    base_headers = {
                        'frame_number': str(frame_number),
                        'original_width': str(width),
                        'original_height': str(height),
                        'header': json.dumps(header_dict)
                    }
                    
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
                else :
                    base_headers = {
                        'frame_number': str(frame_number),
                        'width':str(width),
                        'height':str(height),
                        'header': json.dumps(header_dict)  # This serializes the dictionary to a JSON string
                    }
                    
                    frame0 = video_data.tobytes()
                    self._publish_frame_to_nats(frame0, headers=base_headers)
                
                good_frames += 1
                
            else:
                bad_frames += 1
                
            elapsed_time = (time.monotonic() - start_time) * u.second
            
            n=1
            FRAME_SIZE_MB = 40.0
            mbps = (good_frames * FRAME_SIZE_MB/n) /(time.monotonic() - start_time)
            fps = get_quantity_value(good_frames / elapsed_time)
            
            self.logger.info("Captured {} of {} frames in {:.2f} ({:.2f} fps), {} frames lost, Throughput: {:.2f} MB/s".format(
                good_frames,
                max_frames,
                elapsed_time,
                fps,
                bad_frames,
                mbps))
            
            # Sleep to maintain the desired frame rate
            TARGET_FPS = frame_rate
            TARGET_PERIOD = 1.0 / TARGET_FPS
            
            # Calculate instantaneous fps (not cumulative)
            if frame_number > 0:
                frame_time = time.monotonic() - frame_start_time
                instantaneous_fps = 1.0 / frame_time if frame_time > 0 else 0
                
                if instantaneous_fps > TARGET_FPS:
                    sleep_time = TARGET_PERIOD - frame_time
                    if sleep_time > 0:
                        print(f"Frame {frame_number}: Sleeping for {sleep_time:.3f} seconds")
                        time.sleep(sleep_time)
                
            frame_start_time = time.monotonic()
            frame_number += 1

        time_taken = time.monotonic() - start_time
        print(f"Time taken: {time_taken} and duration: {duration}")
        
        # if frame_number == max_frames - 1:
        if time_taken > duration_seconds:
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
                self.check_memory_usage()
                if self.memory_usage < self.MEMORY_THRESHOLD:
                    ack = await js.publish(self.memory_subject, data, headers=headers)
                else:
                    ack = await js.publish(self.disk_subject, data, headers=headers)
                
                # Verify acknowledgment
                if ack and ack.seq:
                    return True
                else:
                    raise Exception("No acknowledgment received")
            
            # Run the publish coroutine
            success = loop.run_until_complete(publish())
            if success:
                return True
            
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
    
    def shutdown_single_publisher(self):
        """Safely shut down single-threaded publisher system with proper cleanup."""
        self.logger.info("Shutting down single publisher system...")
        
        try:
            # Just reset the NATS client reference - don't try to close across different loops
            if hasattr(self, 'nats_client'):
                self.logger.debug("Resetting NATS JetStream client")
                self.nats_client = None
            
            if hasattr(self, 'nc'):
                self.logger.debug("Resetting NATS connection")
                # Don't try to close connection across different event loops
                # Just reset the reference and let garbage collection handle it
                self.nc = None
            
            # Get current event loop and close it if it exists and is not running
            try:
                current_loop = asyncio.get_event_loop()
                if current_loop and not current_loop.is_running() and not current_loop.is_closed():
                    self.logger.debug("Closing existing event loop")
                    current_loop.close()
            except RuntimeError:
                # No event loop exists, which is fine
                pass
            
            # Clear any event loop from the thread
            try:
                asyncio.set_event_loop(None)
            except Exception as e:
                self.logger.debug(f"Error clearing event loop: {e}")
            
            self.logger.info("Single publisher system shut down complete")
            
        except Exception as e:
            self.logger.error(f"Error during single publisher shutdown: {e}")
