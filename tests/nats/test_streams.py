import pytest
from unittest.mock import AsyncMock, MagicMock
from huntsman.pocs.nats.streams import setup_streams, delete_streams, StreamConfig


@pytest.mark.asyncio
async def test_setup_streams_creates_streams():
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

    cfg = StreamConfig(memory_bytes=1_000_000, disk_bytes=2_000_000)
    await setup_streams(js, num_streams=1, cfg=cfg)

    # Check that add_stream was called for both memory and disk
    assert js.add_stream.call_count == 2
    js.add_stream.assert_any_call(
        name="CAMERA_MEMORY_1",
        subjects=["camera.memory.1.>"],
        retention="workqueue",
        storage="memory",
        max_age=60,
        max_msgs=10000,
        max_bytes=cfg.memory_bytes,
        discard="new",
        no_ack=False,
        duplicate_window=60,
    )
    js.add_stream.assert_any_call(
        name="CAMERA_DISK_1",
        subjects=["camera.archive.1.>"],
        retention="interest",
        storage="file",
        max_age=120,
        max_msgs=10000,
        max_bytes=cfg.disk_bytes,
        discard="old",
        no_ack=False,
    )


@pytest.mark.asyncio
async def test_delete_streams_calls_delete_stream(mocker):
    # Mock list_streams to return fake streams
    memory_streams = ["CAMERA_MEMORY_1"]
    disk_streams = ["CAMERA_DISK_1"]
    mocker.patch("your_module.list_streams", new=AsyncMock(
        return_value=(memory_streams, disk_streams)))

    js = MagicMock()
    js.delete_stream = AsyncMock()

    await delete_streams(js)

    # delete_stream should be called for each memory and disk stream
    js.delete_stream.assert_any_call("CAMERA_MEMORY_1")
    js.delete_stream.assert_any_call("CAMERA_DISK_1")
    assert js.delete_stream.call_count == 2
