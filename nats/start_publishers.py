import os
import signal
import subprocess
import sys
import time

# Configuration
NUM_PUBLISHERS = 10
BASE_PORT = 5555
FRAME_SIZE_MB = 8  # Size in MB
FRAME_RATE = 5  # FPS

# List to keep track of processes
processes = []


def signal_handler(sig, frame):
    print("\nShutting down all publishers...")
    for p in processes:
        if p.poll() is None:  # If process is still running
            p.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    print(f"Starting {NUM_PUBLISHERS} ZeroMQ publishers...")

    for i in range(NUM_PUBLISHERS):
        port = BASE_PORT + i
        pub_id = f"pub_{i+1}"

        # Set environment variables
        env = os.environ.copy()
        env["ZMQ_PORT"] = str(port)
        env["FRAME_SIZE_MB"] = str(FRAME_SIZE_MB)
        env["FRAME_RATE"] = str(FRAME_RATE)
        env["PUB_ID"] = pub_id

        # Start the publisher process
        cmd = ["python", "pub.py"]
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

        print(f"Started publisher {pub_id} on port {port}")
        time.sleep(0.5)  # Small delay between starting publishers

    print(f"All {NUM_PUBLISHERS} publishers started")

    # Wait for all processes to complete
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
