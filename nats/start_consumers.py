import os
import signal
import subprocess
import sys
import time

# Configuration
NUM_CONSUMERS = 10
NATS_SERVER = "nats://localhost:4222"

# List to keep track of processes
processes = []


def signal_handler(sig, frame):
    print("\nShutting down all consumers...")
    for p in processes:
        if p.poll() is None:  # If process is still running
            p.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    print(f"Starting {NUM_CONSUMERS} NATS consumers...")

    for i in range(NUM_CONSUMERS):
        consumer_id = i

        # Set environment variables
        env = os.environ.copy()
        env["NATS_SERVER"] = NATS_SERVER
        env["CONSUMER_ID"] = str(consumer_id)

        # Start the consumer process
        cmd = ["python", "consumer.py", str(consumer_id)]
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

        # Small delay to stagger startup
        time.sleep(0.1)

    print(f"Started {NUM_CONSUMERS} consumers. Press Ctrl+C to stop.")

    # Wait for processes to complete or be interrupted
    try:
        while True:
            time.sleep(1)

            # Check if any process has exited
            for i, proc in enumerate(processes[:]):
                if proc.poll() is not None:
                    print(f"Consumer process {i} exited with code {proc.returncode}")
                    processes.remove(proc)

            # If all processes have exited, exit the script
            if not processes:
                print("All consumer processes have exited.")
                break
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
