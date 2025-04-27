import os
import signal
import sys
import time

import fitsio
import numpy as np
import zmq

# Configuration
PORT = int(os.environ.get("ZMQ_PORT", "5555"))
FRAME_SIZE_MB = float(os.environ.get("FRAME_SIZE_MB", "8"))  # Size in MB
FRAME_RATE = float(os.environ.get("FRAME_RATE", "10"))  # FPS
PUB_ID = os.environ.get("PUB_ID", f"pub_{PORT}")

# Calculate frame size in bytes
FRAME_SIZE_BYTES = int(FRAME_SIZE_MB * 1024 * 1024)

# Global flag for shutdown
running = True


def signal_handler(sig, frame):
    global running
    print(f"\n[{PUB_ID}] Shutting down gracefully (CTRL+C detected)...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    # Set up ZeroMQ publisher
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    bind_address = f"tcp://*:{PORT}"
    socket.bind(bind_address)

    print(f"[{PUB_ID}] ZeroMQ publisher started on {bind_address}")
    print(f"[{PUB_ID}] Frame size: {FRAME_SIZE_MB} MB, Frame rate: {FRAME_RATE} FPS")

    # Initialize counters
    frame_count = 0
    start_time = time.time()
    last_report_time = start_time

    # Main loop
    global running

    fits_path = "/home/batbold/Projects/data0/dfnserver_data/frame000000.fits"
    # fits_path = "/home/batbold/Projects/data0/jetson_data/frame000000.fits"
    data, header = fitsio.read(fits_path, header=True)

    while running:
        try:
            # Create a random frame of the specified size
            # frame = np.random.bytes(FRAME_SIZE_BYTES)
            # frame = data[::3, ::3].tobytes()
            frame = data.tobytes()

            # Send the frame
            socket.send(frame)

            # Update counters
            frame_count += 1

            # Report stats periodically
            current_time = time.time()
            if current_time - last_report_time >= 1.0:  # Report every second
                elapsed = current_time - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                mbps = (frame_count * FRAME_SIZE_MB) / elapsed if elapsed > 0 else 0

                if frame_count % 10 == 0:
                    print(
                        f"[{PUB_ID}] Sent frame {frame_count} | "
                        f"FPS: {fps:.2f} | Throughput: {mbps:.2f} MB/s"
                    )

                last_report_time = current_time

            # Sleep to maintain the desired frame rate
            time.sleep(1.0 / FRAME_RATE)

        except Exception as e:
            print(f"[{PUB_ID}] Error: {e}")
            time.sleep(1.0)

        # Check if we should exit
        if not running:
            break

    # Clean up
    socket.close()
    context.term()
    print(f"[{PUB_ID}] Publisher shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{PUB_ID}] Shutting down...")
