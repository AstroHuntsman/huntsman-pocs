#!/usr/bin/env python3
import argparse
import psutil
import json
import time
from typing import Optional


def monitor_memory(memory_threshold: float = 31, check_interval: float = 1, memory_status_file: str = "/var/huntsman/images/memory_status.json", iterations: Optional[int] = None) -> None:
    """Monitor system memory and write status to a JSON file.

    This function periodically checks the system memory usage and writes a status
    JSON file that includes the memory percentage, threshold, and whether
    publishing should pause. It runs asynchronously, allowing other async tasks
    to execute concurrently.


    Args:
        memory_threshold: Percentage of memory usage above which publishing should pause.
        check_interval: Time in seconds between memory checks.
        memory_status_file: Path to JSON file where memory status is written.
        iterations: Number of iterations to run. If None, runs indefinitely.
    """
    if memory_threshold < 0 or memory_threshold > 100:
        print(f"Memory threshold set to invalid value: {memory_threshold}:")
        print(f"Falling back to default memory threshold of 31%")
        memory_threshold = 31

    print(f"Memory monitor started. Threshold: {memory_threshold}%")
    count_iter = 0
    while iterations is None or count_iter < iterations:
        try:
            # Get memory usage
            mem = psutil.virtual_memory()
            used_percent = mem.percent

            # Determine if we should pause publishing
            should_pause = used_percent >= memory_threshold

            # Write status to file
            status = {"timestamp": time.time(), "memory_used_percent": used_percent,
                      "threshold": memory_threshold, "should_pause": should_pause}

            with open(memory_status_file, "w") as f:
                json.dump(status, f)

            if should_pause:
                print(
                    f"WARNING: Memory usage ({used_percent:.1f}%) exceeds threshold ({memory_threshold}%). Publishers should pause.")
            else:
                print(f"Memory usage: {used_percent:.1f}% (threshold: {memory_threshold}%)")

            count_iter += 1
            if iterations is not None and count_iter >= iterations:
                # Break if iterations is reached
                break
            time.sleep(check_interval)

        except Exception as e:
            print(f"Error monitoring memory: {e}")
            time.sleep(check_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory monitor for Huntsman Movie Mode setup")
    parser.add_argument("-m", "--memory_threshold", type=float, default=31,
                        help="The memory threshold. Once memory exceeds this threshold, pause publishign")
    parser.add_argument("-c", "--check_interval", type=float, default=1,
                        help="How frequently (in seconds) to sample the current memory usage")
    parser.add_argument("-f", "--memory_status_file", type=str, default="/var/huntsman/images/memory_status.json",
                        help="The filepath to the memory status file - where memory usage information is stored")
    parser.add_argument("-i", "--iterations", type=Optional[int], default=None,
                        help="The number of times to check the memory usage before exiting. If None, will check indefinitely.")
    args = parser.parse_args()
    monitor_memory(memory_threshold=args.m, check_interval=args.c, memory_status_file=args.f)
