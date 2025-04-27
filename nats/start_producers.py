import os
import signal
import subprocess
import sys
import time

# Configuration
NUM_PRODUCERS = int(os.environ.get("NUM_PRODUCERS", "10"))  # Default to 2 producers
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
FITS_PATH = os.environ.get(
    "FITS_PATH", "/home/batbold/Projects/data0/dfnserver_data/frame000000.fits"
)
# FITS_PATH = os.environ.get("FITS_PATH", "/home/batbold/Projects/data0/jetson_data/frame000000.fits")
MEMORY_THRESHOLD = os.environ.get("MEMORY_THRESHOLD", "31")
MEMORY_STATUS_FILE = os.environ.get("MEMORY_STATUS_FILE", "/tmp/memory_status.json")
FRAME_RATE = os.environ.get("FRAME_RATE", "10")  # Default 1 FPS

# List to keep track of processes
processes = []


def signal_handler(sig, frame):
    print("\nShutting down all producers...")
    for p in processes:
        if p.poll() is None:  # If process is still running
            p.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    print(f"Starting {NUM_PRODUCERS} NATS producers...")

    for i in range(NUM_PRODUCERS):
        producer_id = i  # Use numeric IDs (0, 1) instead of string labels

        # Set environment variables
        env = os.environ.copy()
        env["NATS_SERVER"] = NATS_SERVER
        env["FITS_PATH"] = FITS_PATH
        env["MEMORY_THRESHOLD"] = MEMORY_THRESHOLD
        env["MEMORY_STATUS_FILE"] = MEMORY_STATUS_FILE
        env["PRODUCER_ID"] = str(producer_id)  # Pass numeric ID as string
        env["FRAME_RATE"] = FRAME_RATE

        # Start the producer process
        cmd = ["python", "producer.py", str(producer_id)]  # Pass numeric ID as string
        print(f"Starting producer {producer_id} with ID {producer_id}")
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

        # Small delay to stagger startup
        time.sleep(0.1)

    print(f"All {NUM_PRODUCERS} producers started")

    # Wait for processes to complete or be interrupted
    try:
        while True:
            time.sleep(1)

            # Check if any process has exited
            for i, proc in enumerate(processes[:]):
                if proc.poll() is not None:
                    print(f"Producer process {i} exited with code {proc.returncode}")
                    processes.remove(proc)

            # If all processes have exited, exit the script
            if not processes:
                print("All producer processes have exited.")
                break
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
