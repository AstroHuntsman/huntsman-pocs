import asyncio
import nats
import signal
import sys
import time
import os
import json
import fitsio  # Added fitsio for writing FITS files
import numpy as np  # Added for handling frame data
from datetime import datetime, timezone  # Added for timestamp handling
import threading
import queue
from astropy.io import fits

# Flag to control the consumer loop
running = True

# Configuration - can be overridden by environment variables
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/home/batbold/Projects/huntsman/images")  # Default output directory
COMPRESS = os.environ.get("COMPRESS", "RICE")  # Default compression method
DISABLE_FILE_WRITING = os.environ.get("DISABLE_FILE_WRITING", "False").lower() == "true"
NUM_WRITER_THREADS = int(os.environ.get("NUM_WRITER_THREADS", "4"))  # Number of writer threads

# Create file writing queue
file_write_queue = queue.Queue()

def signal_handler(sig, frame):
    global running
    print("Shutting down...")
    running = False


def write_fits(data, header, filename, exposure_event=None, **kwargs):
    """Write FITS file to requested location.

    >>> from panoptes.utils.images import fits as fits_utils
    >>> data = np.random.normal(size=100)
    >>> header = { 'FILE': 'delete_me', 'TEST': True }
    >>> filename = str(getfixture('tmpdir').join('temp.fits'))
    >>> fits_utils.write_fits(data, header, filename)
    >>> assert os.path.exists(filename)

    >>> fits_utils.getval(filename, 'FILE')
    'delete_me'
    >>> data2 = fits_utils.getdata(filename)
    >>> assert np.array_equal(data, data2)

    Args:
        data (array_like): The data to be written.
        header (dict): Dictionary of items to be saved in header.
        filename (str): Path to filename for output.
        exposure_event (None|`threading.Event`, optional): A `threading.Event` that
            can be triggered when the image is written.
        kwargs (dict): Options that are passed to the `astropy.io.fits.PrimaryHDU.writeto`
            method.
    """
    if not isinstance(header, fits.Header):
        header = fits.Header(header)

    hdu = fits.PrimaryHDU(data, header=header)

    # Create directories if required.
    if os.path.dirname(filename):
        os.makedirs(os.path.dirname(filename), mode=0o775, exist_ok=True)

    try:
        hdu.writeto(filename, **kwargs)
    except OSError as err:
        print(f'Error writing image to {filename}: {err!r}')
    else:
        print(f'Image written to {filename}')
    finally:
        if exposure_event:
            exposure_event.set()


def write_fits_file(data, header, filename, compress=None):
    """Write data to a FITS file using fitsio.
    
    Args:
        data: The image data array
        header: Dictionary containing FITS header information
        filename: Full path to the output file
        compress: Compression method (RICE, GZIP, PLIO, or None)
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        # Write the file with fitsio
        fitsio.write(filename, data, header=header, compress=compress, clobber=True)
        return True
    except Exception as e:
        print(f"Error writing FITS file {filename}: {e}")
        return False


# Writer thread function
def file_writer_thread(thread_id):
    print(f"Starting writer thread {thread_id}")
    while running:
        try:
            # Get item from queue with timeout
            try:
                item = file_write_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            # Extract data from queue item
            frame_data, header, filepath = item
            
            # Write the file
            write_fits(frame_data, header, filepath)
            print(f"Writer {thread_id}: Saved frame to {filepath}")
            
            # Mark task as done
            file_write_queue.task_done()
        except Exception as e:
            print(f"Writer {thread_id}: Error writing file: {e}")
            # Mark task as done even if it failed
            try:
                file_write_queue.task_done()
            except:
                pass
    
    print(f"Writer thread {thread_id} shutdown")


def is_chunked_data(msg):
    """
    Determine if the message contains chunked data by checking for chunk-related headers.
    
    Args:
        msg: NATS message with headers
        
    Returns:
        bool: True if the data is chunked, False otherwise
    """
    if not hasattr(msg, 'headers') or not msg.headers:
        return False
    
    # Check for any chunk-related headers
    chunk_indicators = [
        'chunk_x', 'chunk_y', 'chunk_number', 'chunk_order',
        'x_start', 'y_start', 'x_end', 'y_end',
        'total_chunks_x', 'total_chunks_y'
    ]
    
    return any(indicator in msg.headers for indicator in chunk_indicators)


def create_fits_header_chunked(msg, consumer_id):
    """
    Create a properly formatted FITS header from NATS message headers for chunked data.
    
    Args:
        msg: NATS message with headers
        consumer_id: ID of the consumer processing this message
        
    Returns:
        fits.Header: Header object with all message metadata
    """
    # Start with an empty header
    header = fits.Header()
    
    # Get dimensions first to ensure they're placed correctly in the header
    width = height = None
    if hasattr(msg, 'headers'):
        if 'width' in msg.headers:
            width = int(msg.headers['width'])
        if 'height' in msg.headers:
            height = int(msg.headers['height'])
    
    # Create a new HDU with the dimensions to ensure correct card order
    if width is not None and height is not None:
        # Using PrimaryHDU initializes a proper FITS header with SIMPLE, BITPIX, NAXIS, NAXIS1, NAXIS2
        # in the correct order
        empty_data = np.zeros((height, width), dtype=np.uint16)
        temp_hdu = fits.PrimaryHDU(data=empty_data)
        header = temp_hdu.header
    
    # Set default timestamp
    header['DATE-OBS'] = datetime.now(timezone.utc).isoformat()
    
    # Add consumer ID
    header['CONSUMER'] = str(consumer_id)
    
    # If message has no headers, return the basic header
    if not hasattr(msg, 'headers') or not msg.headers:
        return header
    
    # Process all headers from the message
    for key, value in msg.headers.items():
        if key == 'header':
            # Handle the JSON serialized header
            try:
                header_dict = json.loads(value)
                # Add all items from the parsed header
                for hkey, hvalue in header_dict.items():
                    # Skip dimension keys - we already handled them
                    if hkey in ['NAXIS', 'NAXIS1', 'NAXIS2']:
                        continue
                    # Skip keys that are too long for FITS standard (8 chars)
                    if len(str(hkey)) <= 8:
                        header[hkey] = hvalue
            except Exception as e:
                print(f"Error parsing header JSON: {e}")
        elif key in ['frame_number', 'chunk_x', 'chunk_y', 
                    'x_start', 'y_start', 'x_end', 'y_end', 
                    'total_chunks_x', 'total_chunks_y', 'chunk_order', 'chunk_number']:
            # Add these special fields with descriptive comments
            # Skip width and height as they're handled separately
            if key == 'frame_number':
                header['FRAMENO'] = (int(value), 'Frame sequence number')
            elif key == 'chunk_x':
                header['CHUNX'] = (int(value), 'X position of chunk in grid')
            elif key == 'chunk_y':
                header['CHUNY'] = (int(value), 'Y position of chunk in grid')
            elif key == 'x_start':
                header['XSTART'] = (int(value), 'X start pixel in original frame')
            elif key == 'y_start':
                header['YSTART'] = (int(value), 'Y start pixel in original frame')
            elif key == 'x_end':
                header['XEND'] = (int(value), 'X end pixel in original frame')
            elif key == 'y_end':
                header['YEND'] = (int(value), 'Y end pixel in original frame')
            elif key == 'total_chunks_x':
                header['TCHUNKX'] = (int(value), 'Total chunks in X direction')
            elif key == 'total_chunks_y':
                header['TCHUNKY'] = (int(value), 'Total chunks in Y direction')
            elif key == 'chunk_order' or key == 'chunk_number':
                header['CHUNKNO'] = (int(value), 'Linear chunk number')
        elif key not in ['width', 'height']:  # Skip width/height, already handled
            # Make sure the key is FITS-compliant (8 chars or less)
            fits_key = key[:8].upper()
            header[fits_key] = value
    
    return header


def create_fits_header_nochunk(msg, consumer_id):
    """
    Create a FITS header for non-chunked data.
    
    Args:
        msg: NATS message with headers
        consumer_id: ID of the consumer processing this message
        
    Returns:
        fits.Header: Header object with message metadata
    """
    # Get header if available
    header = {}
    if hasattr(msg, 'headers') and 'header' in msg.headers:
        try:
            # Parse JSON header if available
            header_dict = json.loads(msg.headers['header'])
            header = fits.Header(header_dict)
        except Exception as e:
            print(f"Error parsing header: {e}")
            # Use basic header as fallback
            header = fits.Header()
            header['DATE-OBS'] = datetime.now(timezone.utc).isoformat()
    else:
        # Create a basic header if none provided
        header = fits.Header()
        header['DATE-OBS'] = datetime.now(timezone.utc).isoformat()
    
    # Add consumer ID to header
    header['CONSUMER'] = str(consumer_id)
    
    return header


def process_frame_data(msg, consumer_id, stream_type):
    """
    Process frame data from a NATS message, handling both chunked and non-chunked data.
    
    Args:
        msg: NATS message containing frame data
        consumer_id: ID of the consumer processing this message
        stream_type: "memory" or "disk" to indicate the stream type
        
    Returns:
        tuple: (frame_data, header, filepath) or None if processing failed
    """
    if len(msg.data) == 0:
        return None
    
    # Get dimensions from headers
    width = height = None
    if hasattr(msg, 'headers'):
        if 'width' in msg.headers:
            width = int(msg.headers['width'])
        if 'height' in msg.headers:
            height = int(msg.headers['height'])
    
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
        # Try to guess a square shape
        size = int(np.sqrt(len(frame_data)))
        if size * size == len(frame_data):
            frame_data = frame_data.reshape((size, size))

    print(f"{stream_type}_frame_data.shape:", frame_data.shape)
    print(f"{stream_type}_frame_data[0][0]: {frame_data[0,0]}")
    
    # Determine if data is chunked and create appropriate header
    is_chunked = is_chunked_data(msg)
    
    if is_chunked:
        print(f"Consumer {consumer_id}: Processing chunked data")
        header = create_fits_header_chunked(msg, consumer_id)
    else:
        print(f"Consumer {consumer_id}: Processing non-chunked data")
        header = create_fits_header_nochunk(msg, consumer_id)
    
    # Create filename with timestamp and chunk info if available
    frame_number = msg.headers.get('frame_number', '0') if hasattr(msg, 'headers') else '0'
    chunk_info = ""
    
    if is_chunked and hasattr(msg, 'headers'):
        if 'chunk_x' in msg.headers and 'chunk_y' in msg.headers:
            chunk_info = f"_chunk_{msg.headers['chunk_x']}_{msg.headers['chunk_y']}"
        elif 'chunk_number' in msg.headers:
            chunk_info = f"_chunk_{msg.headers['chunk_number']}"
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f"frame_{stream_type}_{consumer_id}_{frame_number}{chunk_info}_{timestamp_str}.fits"
    filepath = os.path.join(OUTPUT_DIR, str(consumer_id), stream_type, filename)
    
    return frame_data, header, filepath


async def process_memory_stream(consumer_id, memory_sub, stats):
    while running:
        try:
            memory_msgs = await memory_sub.fetch(batch=100, timeout=0.5)
            for msg in memory_msgs:
                # Display headers if available
                if hasattr(msg, 'headers') and msg.headers:
                    header_info = ", ".join([f"{k}={v}" for k, v in msg.headers.items()])
                    print(f"Consumer {consumer_id}: Received frame with headers: {header_info}")
                
                # Process the frame data
                result = process_frame_data(msg, consumer_id, "memory")
                if result:
                    frame_data, header, filepath = result
                    
                    # Add to write queue
                    file_write_queue.put((frame_data, header, filepath))
                    print(f"Added memory frame to write queue, queue size: {file_write_queue.qsize()}")
                
                await msg.ack()
                stats["memory_count"] += 1
                stats["total_count"] += 1
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"Consumer {consumer_id}: Memory stream error: {e}")
        await asyncio.sleep(0.01)


async def process_disk_stream(consumer_id, disk_sub, stats):
    while running:
        try:
            disk_msgs = await disk_sub.fetch(batch=100, timeout=0.5)
            for msg in disk_msgs:
                # Display headers if available
                if hasattr(msg, 'headers') and msg.headers:
                    header_info = ", ".join([f"{k}={v}" for k, v in msg.headers.items()])
                    print(f"Consumer {consumer_id}: Received disk frame with headers: {header_info}")
                
                # Process the frame data
                result = process_frame_data(msg, consumer_id, "disk")
                if result:
                    frame_data, header, filepath = result
                    
                    # Add to write queue
                    file_write_queue.put((frame_data, header, filepath))
                    print(f"Added disk frame to write queue, queue size: {file_write_queue.qsize()}")
                
                await msg.ack()
                stats["disk_count"] += 1
                stats["total_count"] += 1
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"Consumer {consumer_id}: Disk stream error: {e}")
        await asyncio.sleep(0.01)


async def report_stats(consumer_id, stats):
    start_time = time.time()
    last_report_time = start_time
    
    while running:
        await asyncio.sleep(5.0)  # Report every 5 seconds
        
        current_time = time.time()
        elapsed = current_time - start_time
        fps = stats["total_count"] / elapsed if elapsed > 0 else 0
        
        if stats["total_count"] > 0:  # Only report if we've processed messages
            queue_size = file_write_queue.qsize()
            print(f"Consumer {consumer_id}: Processed {stats['total_count']} frames ({stats['memory_count']} memory, {stats['disk_count']} disk), {fps:.2f} FPS, Queue size: {queue_size}")
        
        last_report_time = current_time


async def run_consumer(consumer_id):
    # Print settings information
    if not DISABLE_FILE_WRITING:
        # Ensure output directories exist for both memory and disk streams
        memory_dir = os.path.join(OUTPUT_DIR, str(consumer_id), "memory")
        disk_dir = os.path.join(OUTPUT_DIR, str(consumer_id), "disk")
        os.makedirs(memory_dir, exist_ok=True)
        os.makedirs(disk_dir, exist_ok=True)
        
        print(f"Consumer {consumer_id}: Saving frames to {OUTPUT_DIR}")
        print(f"Consumer {consumer_id}: Using compression: {COMPRESS}")
        print(f"Consumer {consumer_id}: Using {NUM_WRITER_THREADS} writer threads")
        print(f"Consumer {consumer_id}: Adaptive mode - will handle both chunked and non-chunked data")
    else:
        print(f"Consumer {consumer_id}: File writing disabled - frames will be processed but not saved")

    # Start writer threads
    writer_threads = []
    for i in range(NUM_WRITER_THREADS):
        t = threading.Thread(target=file_writer_thread, args=(i,), daemon=True)
        t.start()
        writer_threads.append(t)
    
    # Connect to NATS
    nc = await nats.connect(servers=[NATS_SERVER])
    js = nc.jetstream()
    
    # Define streams and subjects based on consumer ID
    memory_stream = f"CAMERA_MEMORY_{consumer_id}"
    disk_stream = f"CAMERA_DISK_{consumer_id}"
    memory_subject = f"camera.memory.{consumer_id}.>"
    disk_subject = f"camera.archive.{consumer_id}.>"
    
    # Create consumer names
    memory_consumer_name = f"memory_consumer_{consumer_id}"
    disk_consumer_name = f"disk_consumer_{consumer_id}"
    
    try:
        # Create pull consumers for memory stream
        try:
            # First try to create the consumer
            await js.add_consumer(memory_stream, nats.jetstream.ConsumerConfig(
                durable_name=memory_consumer_name,
                ack_policy="explicit",
                deliver_policy="all"
            ))
            print(f"Consumer {consumer_id}: Created memory consumer {memory_consumer_name}")
        except Exception as e:
            # Consumer might already exist
            print(f"Consumer {consumer_id}: Memory consumer setup note: {e}")
        
        # Subscribe to memory stream
        memory_sub = await js.pull_subscribe(
            memory_subject, 
            memory_consumer_name,
            stream=memory_stream
        )
        print(f"Consumer {consumer_id}: Subscribed to memory stream {memory_stream}")
        
        # Create pull consumers for disk stream
        try:
            # First try to create the consumer
            await js.add_consumer(disk_stream, nats.jetstream.ConsumerConfig(
                durable_name=disk_consumer_name,
                ack_policy="explicit",
                deliver_policy="all"
            ))
            print(f"Consumer {consumer_id}: Created disk consumer {disk_consumer_name}")
        except Exception as e:
            # Consumer might already exist
            print(f"Consumer {consumer_id}: Disk consumer setup note: {e}")
        
        # Subscribe to disk stream
        disk_sub = await js.pull_subscribe(
            disk_subject, 
            disk_consumer_name,
            stream=disk_stream
        )
        print(f"Consumer {consumer_id}: Subscribed to disk stream {disk_stream}")
        
        # Create shared stats dictionary
        stats = {
            "total_count": 0,
            "memory_count": 0,
            "disk_count": 0
        }
        
        # Launch parallel tasks
        memory_task = asyncio.create_task(process_memory_stream(consumer_id, memory_sub, stats))
        disk_task = asyncio.create_task(process_disk_stream(consumer_id, disk_sub, stats))
        stats_task = asyncio.create_task(report_stats(consumer_id, stats))
        
        # Wait for all tasks to complete
        try:
            await asyncio.gather(memory_task, disk_task, stats_task)
        except Exception as e:
            print(f"Consumer {consumer_id}: Error in parallel processing: {e}")
        
    except Exception as e:
        print(f"Consumer {consumer_id}: Setup error: {e}")
    finally:
        # Clean up
        if nc.is_connected:
            await nc.close()
        
        # Wait for the queue to empty
        try:
            print(f"Consumer {consumer_id}: Waiting for file write queue to empty ({file_write_queue.qsize()} items)...")
            file_write_queue.join()
        except:
            pass
            
        print(f"Consumer {consumer_id}: Shutdown complete")


async def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get consumer ID from command line or environment
    consumer_id = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("CONSUMER_ID", "0"))
    
    print(f"Starting adaptive tiered consumer {consumer_id} with {NUM_WRITER_THREADS} writer threads")
    
    # Run consumer
    await run_consumer(consumer_id)


if __name__ == "__main__":
    asyncio.run(main())
