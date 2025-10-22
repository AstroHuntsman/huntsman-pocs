from dataclasses import dataclass, asdict, field
from typing import Optional, List, Tuple

from nats.js import JetStreamContext, api

from huntsman.pocs.nats.utils import subject_from_stream_name


@dataclass
class MemoryStreamConfig(api.StreamConfig):
    """Stream Configuration for memory stream. Gives sensible defaults for the official StreamConfig object"""
    name: str = field(default="", init=False)
    subjects: List[str] = field(default_factory=list, init=False)
    max_bytes: int = 1_000_000_000
    retention: str = "workqueue",
    storage: str = "memory",
    max_age: Optional[float] = 60,
    max_msgs: Optional[int] = 10000,
    discard: str = "new",
    no_ack: bool = False,
    duplicate_window: float = 60,


@dataclass
class DiskStreamConfig(api.StreamConfig):
    """Stream Configuration for disk stream. Gives sensible defaults for the official StreamConfig object"""
    name: str = field(default="", init=False)
    subjects: List[str] = field(default_factory=list, init=False)
    max_bytes: int = 10_000_000_000
    retention: str = "interest",
    storage: str = "file",
    max_age: Optional[float] = 120,
    max_msgs: Optional[int] = 10000,
    discard: str = "old",
    no_ack: bool = False,


async def start_streams(js: JetStreamContext, num_streams: int, disk_cfg: DiskStreamConfig = DiskStreamConfig(), mem_cfg: MemoryStreamConfig = MemoryStreamConfig()) -> None:
    """Sets up all data streams.

    Args:
        js: The JetStreamContext object
        num_streams: The number os streams(memory and disk) to create
        disk_cfg: The DiskStreamConfig object used for the disk stream configuration
        mem_cfg: The MemoryStreamConfig object used for the memory stream configuration
    """
    print(f"Creating {num_streams} memory streams and {num_streams} disk streams...")

    # Create memory streams
    for i in range(num_streams):
        try:
            stream_no = i+1
            mem_cfg.name = f"CAMERA_MEMORY_{stream_no}"
            mem_cfg.subjects = [subject_from_stream_name(mem_cfg.name)]
            await js.add_stream(**asdict(mem_cfg))
            print(f"Created CAMERA_MEMORY_{stream_no} stream")
        except Exception as e:
            print(f"Error creating CAMERA_MEMORY_{stream_no} stream: {e}")

    # Create  disk streams
    for i in range(num_streams):
        try:
            stream_no = i+1
            disk_cfg.name = f"CAMERA_DISK_{stream_no}"
            disk_cfg.subjects = [subject_from_stream_name(disk_cfg.name)]
            await js.add_stream(**asdict(disk_cfg))
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
