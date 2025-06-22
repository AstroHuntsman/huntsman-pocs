import asyncio
import os
import sys

import nats

# Configuration
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
NUM_STREAMS = int(os.environ.get("NUM_STREAMS", "10"))


async def setup_streams():
    # Connect to NATS
    print(f"Connecting to NATS server at {NATS_SERVER}")
    nc = await nats.connect(servers=[NATS_SERVER])
    js = nc.jetstream()

    print(f"Creating {NUM_STREAMS} memory streams and {NUM_STREAMS} disk streams...")

    # Create multiple memory streams
    for i in range(NUM_STREAMS):
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
    for i in range(NUM_STREAMS):
        try:
            await js.add_stream(
                name=f"CAMERA_DISK_{i}",
                subjects=[f"camera.archive.{i}.>"],
                retention="interest",
                storage="file",
                max_age=120,  # 1 hour
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

    await nc.close()
    print("Stream creation complete")


async def delete_streams():
    # Connect to NATS
    print(f"Connecting to NATS server at {NATS_SERVER}")
    nc = await nats.connect(servers=[NATS_SERVER])
    js = nc.jetstream()

    print(f"Deleting {NUM_STREAMS} memory streams and {NUM_STREAMS} disk streams...")

    # Delete memory streams
    for i in range(NUM_STREAMS):
        try:
            await js.delete_stream(f"CAMERA_MEMORY_{i}")
            print(f"Deleted CAMERA_MEMORY_{i} stream")
        except Exception as e:
            print(f"Error deleting CAMERA_MEMORY_{i} stream: {e}")

    # Delete disk streams
    for i in range(NUM_STREAMS):
        try:
            await js.delete_stream(f"CAMERA_DISK_{i}")
            print(f"Deleted CAMERA_DISK_{i} stream")
        except Exception as e:
            print(f"Error deleting CAMERA_DISK_{i} stream: {e}")

    await nc.close()
    print("Stream deletion complete")


if __name__ == "__main__":
    # Check if we should delete streams
    if len(sys.argv) > 1 and sys.argv[1].lower() == "delete":
        asyncio.run(delete_streams())
    else:
        asyncio.run(setup_streams())
