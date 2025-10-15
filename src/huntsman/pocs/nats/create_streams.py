import argparse
import asyncio
from dataclasses import dataclass

import nats
from nats.js import JetStreamContext

from huntsman.pocs.nats.utils import list_streams


@dataclass
class StreamConfig():
    """Stream Configuration"""
    memory_bytes: int = 1_000_000_000
    disk_bytes: int = 10_000_000_000


async def setup_streams(js: JetStreamContext, num_streams: int, cfg: StreamConfig = StreamConfig()) -> None:
    """Sets up all data streams.

    Args:
        js: The JetStreamContext object
        num_streams: The number os streams (memory and disk) to create
        cfg: The StreamConfig object used for stream configuration
    """
    # Connect to NATS
    print(f"Creating {num_streams} memory streams and {num_streams} disk streams...")

    # Create multiple memory streams
    for i in range(num_streams):
        try:
            stream_no = i+1
            await js.add_stream(
                name=f"CAMERA_MEMORY_{stream_no}",
                subjects=[f"camera.memory.{stream_no}.>"],
                retention="workqueue",
                storage="memory",
                max_age=60,
                max_msgs=10000,
                max_bytes=cfg.memory_bytes,
                discard="new",
                no_ack=False,
                duplicate_window=60,
            )
            print(f"Created CAMERA_MEMORY_{stream_no} stream")
        except Exception as e:
            print(f"Error creating CAMERA_MEMORY_{stream_no} stream: {e}")

    # Create multiple disk streams
    for i in range(num_streams):
        try:
            stream_no = i+1
            await js.add_stream(
                name=f"CAMERA_DISK_{stream_no}",
                subjects=[f"camera.archive.{stream_no}.>"],
                retention="interest",
                storage="file",
                max_age=120,
                max_msgs=10000,
                max_bytes=cfg.disk_bytes,
                discard="old",
                no_ack=False,
            )
            print(f"Created CAMERA_DISK_{stream_no} stream")
        except Exception as e:
            print(f"Error creating CAMERA_DISK_{stream_no} stream: {e}")

    # List all streams
    print("\nListing all streams:")
    streams = await js.streams_info()
    for stream in streams:
        print(f"Stream: {stream.config.name}")
        print(f"  Subjects: {stream.config.subjects}")
        print(f"  Storage: {stream.config.storage}")
        print(f"  Max Age: {stream.config.max_age} seconds")
        print(f"  Max Messages: {stream.config.max_msgs}")
        print(f"  Max Bytes: {stream.config.max_bytes} bytes")
        print()

    print("Stream creation complete")


async def delete_streams(js: JetStreamContext) -> None:
    """Deletes all streams for a jetstream context

    Args:
        js: The JetStreamContext object
    """

    memory_streams, disk_streams = await list_streams(js)
    print(f"Deleting {len(memory_streams)} memory streams and {len(disk_streams)} disk streams...")

    for stream in memory_streams + disk_streams:
        try:
            await js.delete_stream(stream)
            print(f"Deleted stream: {stream}")
        except Exception as e:
            print(f"Error deleting '{stream}' stream: {e}")
    print("Stream deletion complete")


async def start(nats_server: str, num_streams: int, cfg: StreamConfig = StreamConfig()) -> None:
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
        await setup_streams(js, num_streams, cfg)
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
        if delete:
            await delete_streams(js)
    finally:
        await nc.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Setup and run a NATS Jetstream streams. Or tear down existing streams.")
    parser.add_argument("--delete", action="store_true", default=False,
                        help="Whether to delete streams previously created, instead of creating new streams.")
    parser.add_argument("-s", "--nats-server", default="nats://localhost:4222",
                        help="The nats server host and port.")
    parser.add_argument("-n", "--num-streams", type=int, default=10,
                        help="The number of streams to create.")

    cfg = StreamConfig()
    parser.add_argument("-m", "--memory-bytes", default=cfg.memory_bytes, type=int,
                        help="The size of the memory stream in bytes")
    parser.add_argument("-d", "--disk-bytes", default=cfg.disk_bytes, type=int,
                        help="The size of the disk stream in bytes")

    args = parser.parse_args()
    if args.delete:
        asyncio.run(delete(nats_server=args.nats_server))
    else:
        cfg = StreamConfig(memory_bytes=args.memory_bytes, disk_bytes=args.disk_bytes)
        asyncio.run(start(nats_server=args.nats_server,
                          num_streams=args.num_streams, cfg=cfg))
