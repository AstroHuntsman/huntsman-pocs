import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import functools
import time
import os
import json
import threading
from typing import Literal, Optional
import queue

from astropy.io import fits
import numpy as np
from nats.js import JetStreamContext
from nats.js import api as jsapi
from nats.aio.msg import Msg

from huntsman.pocs.nats.utils import write_fits, subject_from_stream_name


class ConsumerStats():
    """Class for keeping track of a consumer's statistics"""

    def __init__(self):
        self.memory_count = 0
        self.disk_count = 0
        self.total_count = 0

    def increment(self, stream_type: Optional[Literal["memory", "disk"]]) -> None:
        self.total_count += 1
        if stream_type == "memory":
            self.memory_count += 1
        elif stream_type == "disk":
            self.disk_count += 1
        else:
            print(f"Found invalid stream type: {stream_type}")


@dataclass
class ConsumerConfig():
    """This class exists to store defaults and synchronise them with the
    Consumer class and the __main__ argparse arguments"""
    consumer_output_dir: str = "Projects/huntsman/images"
    compression_method: str = "RICE"
    disable_file_writing: bool = False
    num_writer_threads: int = 4


class Consumer():
    def __init__(self, cfg: ConsumerConfig, js: JetStreamContext, consumer_id: str):
        self.cfg = cfg
        self.js = js
        self.consumer_id = consumer_id
        self.running = True
        self.file_write_queue = queue.Queue()
        self.stats = ConsumerStats()

        if not self.cfg.disable_file_writing:
            print(f"Consumer {self.consumer_id}: Saving frames to {self.cfg.consumer_output_dir}")
            print(f"Consumer {self.consumer_id}: Using compression: {self.cfg.compression_method}")
            print(f"Consumer {self.consumer_id}: Using {self.cfg.num_writer_threads} writer threads")
            print(
                f"Consumer {self.consumer_id}: Adaptive mode - will handle both chunked and non-chunked data")
        else:
            print(
                f"Consumer {self.consumer_id}: File writing disabled - frames will be processed but not saved")

    async def shutdown(self):
        if not self.running:
            return  # Prevent double-shutdown
        print("Shutting down tiered storage manager...")
        self.running = False

    def file_writer_thread(self, thread_id: int):
        print(f"Starting writer thread {thread_id}")
        while self.running:
            try:
                # Get item from queue with timeout
                try:
                    frame_data, header, filepath = self.file_write_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                write_fits(frame_data, header, filepath)
                print(f"Writer {thread_id}: Saved frame to {filepath}")
                self.file_write_queue.task_done()
            except Exception as e:
                print(f"Writer {thread_id}: Error writing file: {e}")
                # Mark task as done even if it failed
                try:
                    self.file_write_queue.task_done()
                except BaseException:
                    pass

        print(f"Writer thread {thread_id} shutdown")

    def start_writer_threads(self):
        """Begins the writer threads"""
        writer_threads = []
        for i in range(self.cfg.num_writer_threads):
            t = threading.Thread(target=self.file_writer_thread, args=(i,), daemon=True)
            t.start()
            writer_threads.append(t)

    def is_chunked_data(self, msg: Msg) -> bool:
        """
        Determine if the message contains chunked data by checking for chunk-related headers.

        Args:
            msg: NATS message with headers

        Returns:
            bool: True if the data is chunked, False otherwise
        """
        if not hasattr(msg, "headers") or not msg.headers:
            return False

        # Check for any chunk-related headers
        chunk_indicators = [
            "chunk_x",
            "chunk_y",
            "chunk_number",
            "chunk_order",
            "x_start",
            "y_start",
            "x_end",
            "y_end",
            "total_chunks_x",
            "total_chunks_y",
        ]

        return any(indicator in msg.headers for indicator in chunk_indicators)

    def create_fits_header_chunked(self, msg: Msg) -> fits.Header:
        """Create a properly formatted FITS header from NATS message headers for chunked data.

        Args:
            msg: NATS message with headers

        Returns:
            fits.Header: Header object with all message metadata
        """
        # Start with an empty header
        header = fits.Header()

        # Get dimensions first to ensure they're placed correctly in the header
        width = height = None
        if hasattr(msg, "headers"):
            if "width" in msg.headers:
                width = int(msg.headers["width"])
            if "height" in msg.headers:
                height = int(msg.headers["height"])

        # Create a new HDU with the dimensions to ensure correct card order
        if width is not None and height is not None:
            # Using PrimaryHDU initializes a proper FITS header with SIMPLE, BITPIX, NAXIS, NAXIS1, NAXIS2
            # in the correct order
            empty_data = np.zeros((height, width), dtype=np.uint16)
            temp_hdu = fits.PrimaryHDU(data=empty_data)
            header = temp_hdu.header

        # Set default timestamp
        header["DATE-OBS"] = datetime.now(timezone.utc).isoformat()
        header["CONSUMER"] = str(self.consumer_id)

        # If message has no headers, return the basic header
        if not hasattr(msg, "headers") or not msg.headers:
            return header

        # Process all headers from the message
        for key, value in msg.headers.items():
            if key == "header":
                # Handle the JSON serialized header
                try:
                    header_dict = json.loads(value)
                    # Add all items from the parsed header
                    for hkey, hvalue in header_dict.items():
                        # Skip dimension keys - we already handled them
                        if hkey in ["NAXIS", "NAXIS1", "NAXIS2"]:
                            continue
                        # Skip keys that are too long for FITS standard (8 chars)
                        if len(str(hkey)) <= 8:
                            header[hkey] = hvalue
                except Exception as e:
                    print(f"Error parsing header JSON: {e}")
            elif key in [
                "frame_number",
                "chunk_x",
                "chunk_y",
                "x_start",
                "y_start",
                "x_end",
                "y_end",
                "total_chunks_x",
                "total_chunks_y",
                "chunk_order",
                "chunk_number",
            ]:
                # Add these special fields with descriptive comments
                # Skip width and height as they're handled separately
                if key == "frame_number":
                    header["FRAMENO"] = (int(value), "Frame sequence number")
                elif key == "chunk_x":
                    header["CHUNX"] = (int(value), "X position of chunk in grid")
                elif key == "chunk_y":
                    header["CHUNY"] = (int(value), "Y position of chunk in grid")
                elif key == "x_start":
                    header["XSTART"] = (int(value), "X start pixel in original frame")
                elif key == "y_start":
                    header["YSTART"] = (int(value), "Y start pixel in original frame")
                elif key == "x_end":
                    header["XEND"] = (int(value), "X end pixel in original frame")
                elif key == "y_end":
                    header["YEND"] = (int(value), "Y end pixel in original frame")
                elif key == "total_chunks_x":
                    header["TCHUNKX"] = (int(value), "Total chunks in X direction")
                elif key == "total_chunks_y":
                    header["TCHUNKY"] = (int(value), "Total chunks in Y direction")
                elif key == "chunk_order" or key == "chunk_number":
                    header["CHUNKNO"] = (int(value), "Linear chunk number")
            elif key not in ["width", "height"]:  # Skip width/height, already handled
                # Make sure the key is FITS-compliant (8 chars or less)
                fits_key = key[:8].upper()
                header[fits_key] = value

        return header

    def create_fits_header_nochunk(self, msg: Msg) -> fits.Header:
        """Create a FITS header for non-chunked data.

        Args:
            msg: NATS message with headers

        Returns:
            fits.Header: Header object with message metadata
        """
        # Get header if available
        header = {}
        if hasattr(msg, "headers") and "header" in msg.headers:
            try:
                # Parse JSON header if available
                header_dict = json.loads(msg.headers["header"])
                header = fits.Header(header_dict)
            except Exception as e:
                print(f"Error parsing header: {e}")
                # Use basic header as fallback
                header = fits.Header()
                header["DATE-OBS"] = datetime.now(timezone.utc).isoformat()
        else:
            # Create a basic header if none provided
            header = fits.Header()
            header["DATE-OBS"] = datetime.now(timezone.utc).isoformat()

        # Add consumer ID to header
        header["CONSUMER"] = str(self.consumer_id)

        return header

    def create_frame_fname(self, msg: Msg, is_chunked: bool) -> str:
        """Create filename with timestamp and chunk info if available

        Args:
            msg: The Nats Jetstream message
            is_chunked: Whether the data is chunked or not
            timestamp: The timestamp to use for the filename. If not supplied, will use system time at runtime.
        """
        frame_number = msg.headers.get("frame_number", "0") if hasattr(msg, "headers") else "0"
        chunk_info = ""
        if is_chunked and hasattr(msg, "headers"):
            if "chunk_x" in msg.headers and "chunk_y" in msg.headers:
                chunk_info = f"_chunk_{msg.headers['chunk_x']}_{msg.headers['chunk_y']}"
            elif "chunk_number" in msg.headers:
                chunk_info = f"_chunk_{msg.headers['chunk_number']}"

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"frame_{self.consumer_id}_{frame_number}{chunk_info}_{timestamp_str}.fits"
        return filename

    def process_frame_data(self, msg: Msg) -> Optional[np.ndarray]:
        """Process frame data from a NATS message, handling both chunked and non-chunked data.

        Args:
            msg: NATS message containing frame data

        Returns:
            np.ndarray: processed frame data or None if processing failed
        """
        if len(msg.data) == 0:
            return None

        # Get dimensions from headers
        width = height = None
        if hasattr(msg, "headers"):
            if "width" in msg.headers:
                width = int(msg.headers["width"])
            if "height" in msg.headers:
                height = int(msg.headers["height"])

        # Convert binary data back to numpy array
        # Assume uint16 data type (same as in zwo.py)
        frame_data = np.frombuffer(msg.data, dtype=np.uint16)

        # Reshape to original dimensions if we have them
        if width is not None and height is not None:
            try:
                frame_data = frame_data.reshape((height, width))
            except ValueError as e:
                print(f"Error reshaping data: {e}")
                # If reshape fails, try to guess a square shape
                size = int(np.sqrt(len(frame_data)))
                if size * size == len(frame_data):
                    frame_data = frame_data.reshape((size, size))
                else:
                    raise ValueError("Cannot reshape data to given dimensions or square")
        else:
            # Try to guess a square shape
            size = int(np.sqrt(len(frame_data)))
            if size * size == len(frame_data):
                frame_data = frame_data.reshape((size, size))
            else:
                raise ValueError("Cannot reshape data to a square")

        return frame_data

    async def get_stream_type_from_sub(self, sub: JetStreamContext.PullSubscription) -> Optional[str]:
        """Tries to determine the stream type from a subscription object

        Args:
            sub: The Jetstream Subscription object

        Return:
            Optional[str]: The name of the stream type. None if neither "memory" or "disk" was found.
        """
        consumer_info = await sub.consumer_info()
        if "memory" in consumer_info.stream_name.lower():
            return "memory"
        elif "disk" in consumer_info.stream_name.lower():
            return "disk"
        return None

    async def process_stream(self, sub: JetStreamContext.PullSubscription) -> None:
        """Consume and process messages from a JetStream stream.

        Continuously fetches messages from the given pull subscription 
        processes each frame of data into a FITS file format, and queues it for writing to disk.
        Also updates a shared statistics dictionary with counts of processed frames.

        Args:
            sub: The pull subscription object for the stream.
        """

        output_directory = os.path.join(self.cfg.consumer_output_dir,
                                        "movie", f"consumer_{self.consumer_id}")
        os.makedirs(output_directory, exist_ok=True)
        stream_type = await self.get_stream_type_from_sub(sub)
        while self.running:
            try:
                msgs = await sub.fetch(batch=100, timeout=5)
                for msg in msgs:
                    # Display headers if available
                    if hasattr(msg, "headers") and msg.headers:
                        header_info = ", ".join([f"{k}={v}" for k, v in msg.headers.items()])
                        print(
                            f"Consumer {self.consumer_id}: Received frame with headers: {header_info}")

                    # Process the frame data
                    frame_data = await asyncio.to_thread(functools.partial(self.process_frame_data, msg=msg))
                    if frame_data is not None:
                        is_chunked = self.is_chunked_data(msg)
                        if is_chunked:
                            header = await asyncio.to_thread(functools.partial(self.create_fits_header_chunked, msg=msg))
                        else:
                            header = await asyncio.to_thread(functools.partial(self.create_fits_header_nochunk, msg=msg))
                        filepath = os.path.join(
                            output_directory, self.create_frame_fname(msg, is_chunked))

                        # Add to write queue
                        self.file_write_queue.put((frame_data, header, filepath))
                        print(
                            f"Added frame to write queue, queue size: {self.file_write_queue.qsize()}")

                    await msg.ack()
                    self.stats.increment(stream_type)

                if msgs:
                    await asyncio.sleep(0)  # Yield control
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"Consumer {self.consumer_id}: Stream error: {e}")

    async def report_stats(self) -> None:
        """Periodically report processing statistics for a consumer.

        Runs in a loop, sleeping for 5 seconds between reports and
        prints the number of frames processed, the breakdown between memory and disk streams,
        the effective processing rate (FPS), and the current size of the file write queue.

        Args:
            consumer_id: Identifier for the consumer, used in log messages.
        """
        start_time = time.time()

        while self.running:
            await asyncio.sleep(5.0)  # Report every 5 seconds

            current_time = time.time()
            elapsed = current_time - start_time
            fps = self.stats.total_count / elapsed if elapsed > 0 else 0

            if self.stats.total_count > 0:  # Only report if we've processed messages
                queue_size = self.file_write_queue.qsize()
                print(
                    f"Consumer {self.consumer_id}: Processed {self.stats.total_count} frames ({self.stats.memory_count} memory, {self.stats.disk_count} disk), {fps:.2f} FPS, Queue size: {queue_size}"
                )

    async def setup_memory_consumer(self) -> JetStreamContext.PullSubscription:
        """Starts the memory consumer. Subscribes the consumer to its relevant stream.

       Returns:
           memory_sub: The jetstream memory subscription object
        """
        # Define streams and subjects based on consumer ID
        memory_stream = f"CAMERA_MEMORY_{self.consumer_id}"
        memory_subject = subject_from_stream_name(memory_stream)
        memory_consumer_name = f"memory_consumer_{self.consumer_id}"

        try:
            await self.js.add_consumer(
                memory_stream,
                jsapi.ConsumerConfig(
                    durable_name=memory_consumer_name, ack_policy="explicit", deliver_policy="all"
                ),
            )
            print(f"Consumer {self.consumer_id}: Created memory consumer {memory_consumer_name}")
        except Exception as e:
            print(f"Consumer {self.consumer_id} ERROR: Memory consumer setup note: {e}")
            raise e

        # Subscribe to memory stream
        memory_sub = await self.js.pull_subscribe(memory_subject, memory_consumer_name, stream=memory_stream)
        print(f"Consumer {self.consumer_id}: Subscribed to memory stream {memory_stream}")

        return memory_sub

    async def setup_disk_consumer(self) -> JetStreamContext.PullSubscription:
        """Starts the disk consumer. Subscribes the consumer to its relevant stream.

       Returns:
           memory_sub: The jetstream disk subscription object
        """
        # Define streams and subjects based on consumer ID
        disk_stream = f"CAMERA_DISK_{self.consumer_id}"
        disk_subject = subject_from_stream_name(disk_stream)
        disk_consumer_name = f"disk_consumer_{self.consumer_id}"

        try:
            await self.js.add_consumer(
                disk_stream,
                jsapi.ConsumerConfig(
                    durable_name=disk_consumer_name, ack_policy="explicit", deliver_policy="all"
                ),
            )
            print(f"Consumer {self.consumer_id}: Created disk consumer {disk_consumer_name}")
        except Exception as e:
            print(f"Consumer {self.consumer_id} ERROR: Disk consumer setup note: {e}")
            raise e

        # Subscribe to disk stream
        disk_sub = await self.js.pull_subscribe(disk_subject, disk_consumer_name, stream=disk_stream)
        print(f"Consumer {self.consumer_id}: Subscribed to disk stream {disk_stream}")
        return disk_sub

    async def run_consumer(self, memory_sub: Optional[JetStreamContext.PullSubscription] = None, disk_sub: Optional[JetStreamContext.PullSubscription] = None) -> None:
        """Initialize and run a tiered memory/disk consumer for NATS JetStream.

        Sets up file writer threads, connects to a NATS server, subscribes
        to memory and disk streams using pull subscriptions, and launches tasks to process
        messages from both streams concurrently. It also periodically reports processing
        statistics and ensures graceful shutdown of resources.
        """
        self.start_writer_threads()
        try:
            # Create pull consumers for memory stream and launch async tasks
            if not memory_sub:
                memory_sub = await self.setup_memory_consumer()
            if not disk_sub:
                disk_sub = await self.setup_disk_consumer()

            # Launch stats task
            tasks = []
            tasks.append(asyncio.create_task(self.process_stream(memory_sub)))
            tasks.append(asyncio.create_task(self.process_stream(disk_sub)))
            tasks.append(asyncio.create_task(self.report_stats()))

            # Wait for all tasks to complete
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                print(f"Consumer {self.consumer_id}: Error in parallel processing: {e}")

        except Exception as e:
            print(f"Consumer {self.consumer_id}: Setup error: {e}")
        finally:
            # Wait for the queue to empty
            try:
                print(
                    f"Consumer {self.consumer_id}: Waiting for file write queue to empty ({self.file_write_queue.qsize()} items)..."
                )
                self.file_write_queue.join()
            except BaseException:
                pass

            self.running = False

            print(f"Consumer {self.consumer_id}: Shutdown complete")
