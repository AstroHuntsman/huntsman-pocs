#!/usr/bin/env python3
import asyncio
import argparse

import nats

from huntsman.pocs.nats.monitor import HuntsmanMonitor


async def monitor(nats_server: str = "nats://localhost:4222", check_interval: float = 5, memory_status_file: str = "/var/huntsman/images/memory_status.json", output_file: str = "/var/huntsman/monitor_stats.json") -> None:
    """Monitor system memory and write status to a JSON file.

    This function periodically checks the system memory usage and writes a status
    JSON file that includes the memory percentage, threshold, and whether
    publishing should pause. It runs asynchronously, allowing other async tasks
    to execute concurrently.


    Args:
        nats_server: The nats server address to connect to
        check_interval: Time in seconds between memory checks.
        memory_status_file: Path to JSON file where memory status is written.
        output_file: The path to output the monitor statistics to.
    """
    nc = await nats.connect(nats_server)
    js = nc.jetstream()
    monitor = HuntsmanMonitor(js, memory_status_file=memory_status_file, output_file=output_file)
    await monitor.init_streams()

    print(f"Huntsman monitor started.")
    while True:
        try:
            await monitor.refresh_stats()
            monitor.print_stats()
            monitor.save_stats_to_file()
            asyncio.sleep(check_interval)
        except Exception as e:
            print(f"Error monitoring memory: {e}")
            asyncio.sleep(check_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory monitor for Huntsman Movie Mode setup")
    parser.add_argument("-s", "--nats-server", default="nats://localhost:4222",
                        help="The nats server host and port.")
    parser.add_argument("-c", "--check_interval", type=float, default=5,
                        help="How frequently (in seconds) to sample nats stats")
    parser.add_argument("-f", "--memory_status_file", type=str, default="/var/huntsman/images/memory_status.json",
                        help="The filepath to the memory status file - where memory usage information is stored")
    parser.add_argument("-o", "--stats_output_file", type=str,
                        default="/var/huntsman/monitor_stats.json")
    args = parser.parse_args()
    asyncio.run(monitor(nats_server=args.nats_server, check_interval=args.check_interval,
                memory_status_file=args.memory_status_file, output_file=args.stats_output_file))
