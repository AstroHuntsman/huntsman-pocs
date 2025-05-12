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
import argparse  # Added for argument parsing
from astropy.io import fits

# Flag to control the consumer loop
running = True

# Configuration - can be overridden by environment variables or command line arguments
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/home/batbold/Projects/huntsman/images")  # Default output directory
COMPRESS = os.environ.get("COMPRESS", "RICE")  # Default compression method
DISABLE_FILE_WRITING = False  # Disable file writing for testing

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

async def process_memory_stream(consumer_id, memory_sub, stats):
    while running:
        try:
            memory_msgs = await memory_sub.fetch(batch=100, timeout=0.5)
            for msg in memory_msgs:
                # Display headers if available
                if hasattr(msg, 'headers') and msg.headers:
                    header_info = ", ".join([f"{k}={v}" for k, v in msg.headers.items()])
                    print(f"Consumer {consumer_id}: Received frame with headers: {header_info}")
                
                # Process and save the frame if it contains image data
                if len(msg.data) > 0:
                    # Get dimensions from headers
                    width = height = None
                    if hasattr(msg, 'headers'):
                        # Try to get dimensions from headers
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

                    print("frame_data.shape:", frame_data.shape)
                    print("frame_data[0][0]: {}".format(frame_data[0,0]))
                    
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
                    
                    # Create filename with timestamp
                    frame_number = msg.headers.get('frame_number', '0') if hasattr(msg, 'headers') else '0'
                    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    filename = f"frame_memory_{consumer_id}_{frame_number}_{timestamp_str}.fits"
                    filepath = os.path.join(OUTPUT_DIR, str(consumer_id), "memory", filename)
                    
                    # Write the file
                    write_fits(frame_data, header, filepath)
                    print(f"Saved memory frame to {filepath}")
                
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
                
                # Process and save the frame if it contains image data
                if len(msg.data) > 0:
                    # Get dimensions from headers
                    width = height = None
                    if hasattr(msg, 'headers'):
                        # Try to get dimensions from headers
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

                    print("disk_frame_data.shape:", frame_data.shape)
                    print("disk_frame_data[0][0]: {}".format(frame_data[0,0]))
                    
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
                    
                    # Create filename with timestamp
                    frame_number = msg.headers.get('frame_number', '0') if hasattr(msg, 'headers') else '0'
                    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    filename = f"frame_disk_{consumer_id}_{frame_number}_{timestamp_str}.fits"
                    filepath = os.path.join(OUTPUT_DIR, str(consumer_id), "disk", filename)
                    
                    # Write the file
                    write_fits(frame_data, header, filepath)
                    print(f"Saved disk frame to {filepath}")
                
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
            print(f"Consumer {consumer_id}: Processed {stats['total_count']} frames ({stats['memory_count']} memory, {stats['disk_count']} disk), {fps:.2f} FPS")
        
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
    else:
        print(f"Consumer {consumer_id}: File writing disabled - frames will be processed but not saved")

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
        print(f"Consumer {consumer_id}: Shutdown complete")

async def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get consumer ID from command line or environment
    consumer_id = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("CONSUMER_ID", "0"))
    
    print(f"Starting tiered consumer {consumer_id}")
    
    # Run consumer
    await run_consumer(consumer_id)

if __name__ == "__main__":
    asyncio.run(main()) 