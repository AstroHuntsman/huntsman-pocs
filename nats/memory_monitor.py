#!/usr/bin/env python3
import os
import time
import psutil
import json

# Configuration
MEMORY_THRESHOLD = 31  # Stop publishing when memory usage reaches 31%
CHECK_INTERVAL = 1  # Check every second
STATUS_FILE = "/var/huntsman/images/memory_status.json"

def monitor_memory():
    """Monitor system memory and write status to file"""
    print(f"Memory monitor started. Threshold: {MEMORY_THRESHOLD}%")
    
    while True:
        try:
            # Get memory usage
            mem = psutil.virtual_memory()
            used_percent = mem.percent
            
            # Determine if we should pause publishing
            should_pause = used_percent >= MEMORY_THRESHOLD
            
            # Write status to file
            status = {
                "timestamp": time.time(),
                "memory_used_percent": used_percent,
                "threshold": MEMORY_THRESHOLD,
                "should_pause": should_pause
            }
            
            with open(STATUS_FILE, "w") as f:
                json.dump(status, f)
            
            if should_pause:
                print(f"WARNING: Memory usage ({used_percent:.1f}%) exceeds threshold ({MEMORY_THRESHOLD}%). Publishers should pause.")
            else:
                print(f"Memory usage: {used_percent:.1f}% (threshold: {MEMORY_THRESHOLD}%)")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"Error monitoring memory: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_memory() 