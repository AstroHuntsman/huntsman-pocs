from dataclasses import asdict
import pytest
from unittest.mock import AsyncMock, MagicMock
from huntsman.pocs.nats.streams import start_streams, delete_streams, MemoryStreamConfig, DiskStreamConfig


@pytest.mark.asyncio
@pytest.mark.unit
async def test_start_streams_creates_streams():
    """Typical usage of start streams. Test that it starts the expected streams"""
    js = MagicMock()
    js.add_stream = AsyncMock()
    js.streams_info = AsyncMock(return_value=[
        MagicMock(config=MagicMock(
            name="CAMERA_MEMORY_1",
            subjects=["camera.memory.1.>"],
            storage="memory",
            max_age=60,
            max_msgs=10000,
            max_bytes=1_000_000_000,
        )),
        MagicMock(config=MagicMock(
            name="CAMERA_DISK_1",
            subjects=["camera.archive.1.>"],
            storage="file",
            max_age=120,
            max_msgs=10000,
            max_bytes=10_000_000_000,
        )),
    ])

    disk_cfg = DiskStreamConfig()
    mem_cfg = MemoryStreamConfig()
    await start_streams(js, num_streams=1, disk_cfg=disk_cfg, mem_cfg=mem_cfg)

    # Check that add_stream was called for both memory and disk
    assert js.add_stream.call_count == 2
    mem_cfg.name = "CAMERA_MEMORY_1"
    mem_cfg.subjects = ["camera.memory.1.>"]
    js.add_stream.assert_any_call(**asdict(mem_cfg))
    disk_cfg.name = "CAMERA_DISK_1",
    disk_cfg.subjects = ["camera.archive.1.>"],
    js.add_stream.assert_any_call(**asdict(disk_cfg))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_streams_calls_delete_stream(mocker):
    # Mock list_streams to return fake streams
    memory_streams = ["CAMERA_MEMORY_1"]
    disk_streams = ["CAMERA_DISK_1"]
    mocker.patch("huntsman.pocs.nats.utils.list_streams", new=AsyncMock(
        return_value=(memory_streams, disk_streams)))

    js = AsyncMock()
    js.delete_stream = AsyncMock()

    await delete_streams(js)

    # delete_stream should be called for each memory and disk stream
    js.delete_stream.assert_any_call("CAMERA_MEMORY_1")
    js.delete_stream.assert_any_call("CAMERA_DISK_1")
    assert js.delete_stream.call_count == 2
