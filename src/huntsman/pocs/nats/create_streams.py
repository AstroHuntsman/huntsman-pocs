import argparse
import asyncio
from typing import Optional

import nats
from nats.js import JetStreamContext

from huntsman.pocs.nats.utils import list_streams


async def setup_streams(js: JetStreamContext, num_streams: int):
    # Connect to NATS
    print(f"Creating {num_streams} memory streams and {num_streams} disk streams...")

    # Create multiple memory streams
    for i in range(num_streams):
        try:
            await js.add_stream(
                name=f"CAMERA_MEMORY_{i}",
                subjects=[f"camera.memory.{i}.>"],
                retention="workqueue",
                storage="memory",
                max_age=60,
                max_msgs=10000,
                max_bytes=1_000_000_000,
                discard="new",
                no_ack=False,
                duplicate_window=60,
            )
            print(f"Created CAMERA_MEMORY_{i} stream")
        except Exception as e:
            print(f"Error creating CAMERA_MEMORY_{i} stream: {e}")

    # Create multiple disk streams
    for i in range(num_streams):
        try:
            await js.add_stream(
                name=f"CAMERA_DISK_{i}",
                subjects=[f"camera.archive.{i}.>"],
                retention="interest",
                storage="file",
                max_age=120,
                max_msgs=10000,
                max_bytes=10_000_000_000,  # 10GB per stream
                discard="old",
                no_ack=False,
            )
            print(f"Created CAMERA_DISK_{i} stream")
        except Exception as e:
            print(f"Error creating CAMERA_DISK_{i} stream: {e}")

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


async def main(delete: bool, nats_server: str, num_streams: Optional[int] = None):
    # Connect to NATS
    print(f"Connecting to NATS server at {nats_server}")
    nc = await nats.connect(servers=[nats_server])
    js = nc.jetstream()
    try:
        if delete:
            asyncio.run(delete_streams(js))
        else:
            if not isinstance(num_streams, int):
                raise TypeError(
                    f"Expected int for num_streams, got {type(num_streams)}: {num_streams}")
            asyncio.run(setup_streams(js, num_streams))
    finally:  # Always close connection
        await nc.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Setup and run a NATS Jetstream streams. Or tear down existing streams.")
    parser.add_argument("--delete", action="store_true", default=False,
                        help="Whether to delete streams previously created, instead of creating new streams.")
    parser.add_argument("-s", "--nats-server", default="nats://localhost:4222",
                        help="The nats server host and port.")
    parser.add_argument("-n", "--num-streams", default=10, help="The number of streams to create.")

    args = parser.parse_args()
    asyncio.run(main(**vars(args)))
