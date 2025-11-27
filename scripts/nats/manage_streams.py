import argparse
import asyncio

import nats

from huntsman.pocs.nats.streams import DiskStreamConfig, MemoryStreamConfig, start_streams, delete_streams


async def start(nats_server: str, num_streams: int, disk_cfg: DiskStreamConfig = DiskStreamConfig(), mem_cfg: MemoryStreamConfig = MemoryStreamConfig()) -> None:
    """Connects to the nats server, creates the Jetstream context and Begins
    all streams

    Args:
        nats_server: The hostname of the nats server to start the streams
        num_streams: The number os streams (memory and disk) to create
        cfg: The StreamConfig object used for stream configuration
    """
    # Connect to NATS
    print(f"Connecting to NATS server at {nats_server}")
    nc = await nats.connect(servers=[nats_server])
    js = nc.jetstream()
    try:
        await start_streams(js, num_streams, disk_cfg=disk_cfg, mem_cfg=mem_cfg)
    finally:  # Always close connection
        await nc.close()


async def delete(nats_server: str):
    """Deletes all streams connected to a nats server:

    Args:
        nats_server: The hostname of the nats server to start the streams
    """
    print("Deleting streams...")
    print(f"Connecting to NATS server at {nats_server}")
    nc = await nats.connect(servers=[nats_server])
    js = nc.jetstream()
    try:
        await delete_streams(js)
    finally:
        await nc.close()


async def _main(args):
    if args.delete:
        await delete(nats_server=args.nats_server)
    else:
        mem_cfg = MemoryStreamConfig(max_bytes=args.memory_bytes)
        disk_cfg = DiskStreamConfig(max_bytes=args.disk_bytes)
        await start(nats_server=args.nats_server,
                    num_streams=args.num_streams, mem_cfg=mem_cfg, disk_cfg=disk_cfg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Setup and run a NATS Jetstream streams. Or tear down existing streams.")
    parser.add_argument("--delete", action="store_true", default=False,
                        help="Whether to delete streams previously created, instead of creating new streams.")
    parser.add_argument("-s", "--nats-server", default="nats://localhost:4222",
                        help="The nats server host and port.")
    parser.add_argument("-n", "--num-streams", type=int, default=10,
                        help="The number of streams to create.")

    mem_cfg = MemoryStreamConfig()
    disk_cfg = DiskStreamConfig()
    parser.add_argument("-m", "--memory-bytes", default=mem_cfg.max_bytes, type=int,
                        help="The size of the memory stream in bytes")
    parser.add_argument("-d", "--disk-bytes", default=disk_cfg.max_bytes, type=int,
                        help="The size of the disk stream in bytes")

    args = parser.parse_args()
    asyncio.run(_main(args))
