# Tests the interaction between the memory and disk streams. When memory usage
# is too high, memory messages should be moved to the disk stream and new
# messages should be written to the disk stream until memory is back below the
# threshold.
import os
import pytest
import pytest_asyncio
from unittest.mock import patch
from tempfile import NamedTemporaryFile
from typing import Tuple

from nats.js.errors import NotFoundError
from nats.js import JetStreamContext
from nats.js.api import StreamConfig

from huntsman.pocs.camera.zwo import Camera
from huntsman.pocs.nats.storage_manager import StorageManager, StorageManagerConfig
from huntsman.pocs.nats.streams import MemoryStreamConfig, DiskStreamConfig, start_streams, delete_streams
from huntsman.pocs.nats.monitor import HuntsmanMonitor
from huntsman.pocs.nats.utils import subject_from_stream_name


@pytest_asyncio.fixture
async def setup_streams(js: JetStreamContext):
    """Fixture that creates memory/disk streams and cleans them up."""
    await js.add_stream(StreamConfig(name="memory_0", subjects=["memory_0.>"], retention="workqueue"))
    await js.add_stream(StreamConfig(name="disk_0", subjects=["disk_0.>"], retention="workqueue"))

    yield ("memory_0", "disk_0")

    try:
        await js.delete_stream("memory_0")
    except NotFoundError:
        pass
    try:
        await js.delete_stream("disk_0")
    except NotFoundError:
        pass


async def publish_messages(js: JetStreamContext, subject: str, n: int):
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())
        print(f"Published to subject: {subject}")


@pytest.fixture
def tmp_memory_file():
    tmp = NamedTemporaryFile(delete=False)
    yield tmp.name
    os.remove(tmp.name)


@pytest.fixture
def storage_manager(js, tmp_memory_file) -> StorageManager:
    cfg = StorageManagerConfig(
        memory_threshold=50, memory_status_file=tmp_memory_file, check_interval=0.1)
    return StorageManager(cfg, js)


@pytest.fixture
def monitor(js, tmp_memory_file):
    output_file = NamedTemporaryFile(delete=False).name
    yield HuntsmanMonitor(js, memory_status_file=tmp_memory_file, output_file=output_file)
    os.remove(output_file)


@pytest.fixture
def stream_configs() -> Tuple[MemoryStreamConfig, DiskStreamConfig]:
    mem = MemoryStreamConfig(max_bytes=1024)
    # Use workqueue for easier testing
    disk = DiskStreamConfig(max_bytes=1024, retention="workqueue")
    return mem, disk


async def run_storage_manager_loop(sm: StorageManager):
    # Patch sleep to stop the loop after one iteration
    async def stop_loop(_):
        sm.running = False
    with patch("huntsman.pocs.nats.storage_manager.asyncio.sleep", new=stop_loop):
        await sm.run()


@pytest.mark.asyncio
async def test_move_messages_to_disk(js: JetStreamContext, storage_manager: StorageManager, monitor: HuntsmanMonitor, stream_configs):
    """Tests that messages are moved from memory to disk stream when the memory
    usage exceeds the threshold.
    """
    mem_cfg, disk_cfg = stream_configs
    try:
        mem_streams, disk_streams = await start_streams(js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
        memory_stream = mem_streams[0].config.name
        disk_stream = disk_streams[0].config.name

        await monitor.refresh_stats()
        assert len(monitor.streams) == 2  # one memory, one disk stream

        await publish_messages(js, subject_from_stream_name(memory_stream), 1)
        await publish_messages(js, subject_from_stream_name(disk_stream), 1)
        await run_storage_manager_loop(storage_manager)
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 100  # Write 100% usage for the next storage manager run
            await monitor.refresh_stats()

        assert len(monitor.streams) == 2
        assert os.path.exists(monitor.output_file)
        assert os.path.exists(monitor.memory_status_file)
        assert monitor.streams[memory_stream].info.state.messages == 1
        assert monitor.streams[disk_stream].info.state.messages == 1

        await publish_messages(js, subject_from_stream_name(memory_stream), 1)
        await publish_messages(js, subject_from_stream_name(disk_stream), 1)

        # Should move memory stream messages to disk stream since we set memory use to 100%
        storage_manager.running = True  # reset the manager to 'running' so it actually does things
        await run_storage_manager_loop(storage_manager)
        await monitor.refresh_stats()
        assert monitor.streams[memory_stream].info.state.messages == 0
        assert monitor.streams[disk_stream].info.state.messages == 4
    finally:
        # Delete streams and ensure they're gone
        await delete_streams(js)
        streams = await js.streams_info()
        assert len(streams) == 0


@pytest.mark.asyncio
async def test_consumer_messages():
    pass


@pytest.mark.asyncio
async def test_camera_stream_publish(js: JetStreamContext, storage_manager: StorageManager, monitor: HuntsmanMonitor, stream_configs):
    """Tests that the camera messages are published to the correct stream 
    depending on the current memory usage
    """

    # TODO: Requires testing the zwo camera
    pass
