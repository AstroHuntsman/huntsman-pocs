import asyncio
import json
import os
import signal
import socket
import sys
import time

import nats
import zmq

# Flag to control the producer loop
running = True

# Configuration - can be overridden by environment variables
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
ZMQ_SUB_ADDRESS = os.environ.get("ZMQ_SUB_ADDRESS", "tcp://localhost:5555")
MEMORY_THRESHOLD = float(os.environ.get("MEMORY_THRESHOLD", "16"))  # Percentage
MEMORY_STATUS_FILE = os.environ.get("MEMORY_STATUS_FILE", "/tmp/memory_status.json")
FRAME_RATE = float(os.environ.get("FRAME_RATE", "10"))  # FPS

# Global variables
memory_usage = 0
last_memory_check = 0


def signal_handler(sig, frame):
    global running
    print("Shutting down...")
    running = False


def check_memory_usage():
    global memory_usage, last_memory_check
    current_time = time.time()

    # Only check every 2 seconds
    if current_time - last_memory_check < 2.0:
        return memory_usage

    try:
        if os.path.exists(MEMORY_STATUS_FILE):
            with open(MEMORY_STATUS_FILE, 'r') as f:
                memory_data = json.load(f)
                memory_usage = memory_data.get('memory_used_percent', 0)
    except Exception as e:
        print(f"Error reading memory status: {e}")

    last_memory_check = current_time
    return memory_usage


async def run_producer(producer_id):
    # Connect to NATS
    nc = await nats.connect(servers=[NATS_SERVER])
    js = nc.jetstream()

    # Define subjects based on producer ID
    memory_subject = f"camera.memory.{producer_id}.frame"
    disk_subject = f"camera.archive.{producer_id}.frame"

    try:
        # Set up ZeroMQ subscriber
        print(f"Producer {producer_id}: Connecting to ZeroMQ at {ZMQ_SUB_ADDRESS}")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(ZMQ_SUB_ADDRESS)
        socket.setsockopt_string(zmq.SUBSCRIBE, "")

        # Set up ZeroMQ poller for non-blocking receives
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)

        # Stats tracking
        msg_count = 0
        memory_msg_count = 0
        disk_msg_count = 0
        start_time = time.time()
        last_report_time = start_time

        print(
            f"Producer {producer_id}: Starting to receive from ZeroMQ and publish at target rate of {FRAME_RATE} FPS"
        )

        # Headers for messages
        headers = {"producer_id": str(producer_id), "timestamp": "", "frame_type": ""}

        # Main publishing loop
        while running:
            try:
                # Check for ZeroMQ messages with a timeout
                socks = dict(poller.poll(10))  # 10ms timeout

                if socket in socks and socks[socket] == zmq.POLLIN:
                    # Receive frame from ZeroMQ
                    frame = socket.recv()

                    # Check memory usage
                    current_memory_usage = check_memory_usage()

                    # Update headers
                    headers["timestamp"] = str(time.time())

                    # Decide where to publish based on memory usage
                    if current_memory_usage < MEMORY_THRESHOLD:
                        # Publish to memory stream
                        headers["frame_type"] = "memory"
                        await js.publish(memory_subject, frame, headers=headers)
                        memory_msg_count += 1
                    else:
                        # Publish to disk stream
                        headers["frame_type"] = "disk"
                        await js.publish(disk_subject, frame, headers=headers)
                        disk_msg_count += 1

                    msg_count += 1

                    # Report stats every 5 seconds
                    current_time = time.time()
                    if current_time - last_report_time >= 5.0:
                        elapsed = current_time - start_time
                        fps = msg_count / elapsed
                        print(
                            f"Producer {producer_id}: Published {msg_count} frames ({memory_msg_count} memory, {disk_msg_count} disk), {fps:.2f} FPS, Memory: {current_memory_usage}%"
                        )
                        last_report_time = current_time
                else:
                    # No message available, sleep briefly
                    await asyncio.sleep(0.001)

            except Exception as e:
                print(f"Producer {producer_id} error: {e}")
                await asyncio.sleep(0.1)

    except Exception as e:
        print(f"Producer {producer_id} setup error: {e}")
    finally:
        # Clean up ZeroMQ resources
        if 'socket' in locals():
            socket.close()
        if 'context' in locals():
            context.term()

        # Close NATS connection
        await nc.close()

        # Print final stats
        if 'start_time' in locals():
            elapsed = time.time() - start_time
            fps = msg_count / elapsed if elapsed > 0 else 0
            print(
                f"Producer {producer_id}: Published {msg_count} frames ({memory_msg_count} memory, {disk_msg_count} disk), {fps:.2f} FPS, Memory: {current_memory_usage}%"
            )

        print(f"Producer {producer_id} shutdown complete")


async def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Get producer ID from command line or environment
    producer_id = None  # Default ID

    # Try to get ID from command line argument
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            producer_id = int(arg)  # Try to convert to int directly
        except ValueError:
            # If argument is something like "producer_1", extract the number
            if "producer_" in arg:
                try:
                    producer_id = int(arg.split("_")[1])
                except (IndexError, ValueError):
                    print(
                        f"Warning: Could not parse producer ID from '{arg}', using default ID 0"
                    )
            else:
                print(f"Warning: Invalid producer ID '{arg}', using default ID 0")

    # If no valid ID from command line, try environment variable
    if producer_id is None:
        try:
            producer_id = int(os.environ.get("PRODUCER_ID", "0"))
        except ValueError:
            env_id = os.environ.get("PRODUCER_ID", "0")
            if "producer_" in env_id:
                try:
                    producer_id = int(env_id.split("_")[1])
                except (IndexError, ValueError):
                    producer_id = 0
            else:
                producer_id = 0

    print(f"Starting producer {producer_id}, connected to ZeroMQ at {ZMQ_SUB_ADDRESS}")

    # Run producer
    await run_producer(producer_id)


if __name__ == "__main__":
    asyncio.run(main())
