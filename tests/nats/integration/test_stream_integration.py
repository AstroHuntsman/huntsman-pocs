# Tests the interaction between the memory and disk streams. When memory usage
# is too high, memory messages should be moved to the disk stream and new
# messages should be written to the disk stream until memory is back below the
# threshold.
import os
import pytest
from unittest.mock import patch

from nats.js import JetStreamContext

from huntsman.pocs.nats.storage_manager import StorageManager
from huntsman.pocs.nats.streams import start_streams, delete_streams
from huntsman.pocs.nats.monitor import HuntsmanMonitor
from huntsman.pocs.nats.utils import subject_from_stream_name


async def publish_messages(js: JetStreamContext, subject: str, n: int):
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())
        print(f"Published to subject: {subject}")


async def run_storage_manager_loop(sm: StorageManager):
    # Patch sleep to stop the loop after one iteration
    async def stop_loop(_):
        sm.running = False
    with patch("huntsman.pocs.nats.storage_manager.asyncio.sleep", new=stop_loop):
        await sm.run()


@pytest.mark.asyncio
async def test_stream_start_stop(js: JetStreamContext, stream_configs):
    mem_cfg, disk_cfg = stream_configs
    mem_streams, disk_streams = await start_streams(js, num_streams=2, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    memory_stream_1 = mem_streams[0].config.name
    memory_stream_2 = mem_streams[1].config.name
    disk_stream_1 = disk_streams[0].config.name
    disk_stream_2 = disk_streams[1].config.name

    assert memory_stream_1 == "CAMERA_MEMORY_1"
    assert memory_stream_2 == "CAMERA_MEMORY_2"
    assert disk_stream_1 == "CAMERA_DISK_1"
    assert disk_stream_2 == "CAMERA_DISK_2"

    await delete_streams(js)
    streams = await js.streams_info()
    assert len(streams) == 0


@pytest.mark.asyncio
async def test_move_messages_to_disk(storage_manager: StorageManager, monitor: HuntsmanMonitor, stream_configs):
    """Tests that messages are moved from memory to disk stream when the memory
    usage exceeds the threshold.
    """
    mem_cfg, disk_cfg = stream_configs
    mem_streams, disk_streams = await start_streams(monitor.js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    memory_stream = mem_streams[0].config.name
    disk_stream = disk_streams[0].config.name

    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.percent = 10  # Assure we use memory for this
        await monitor.refresh_stats()
    assert len(monitor.streams) == 2  # one memory, one disk stream

    await publish_messages(monitor.js, subject_from_stream_name(memory_stream), 1)
    await publish_messages(monitor.js, subject_from_stream_name(disk_stream), 1)
    await run_storage_manager_loop(storage_manager)
    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.percent = 100  # Write 100% usage for the next storage manager run
        await monitor.refresh_stats()

    assert len(monitor.streams) == 2
    assert os.path.exists(monitor.output_file)
    assert os.path.exists(monitor.memory_status_file)
    assert monitor.streams[memory_stream].info.state.messages == 1
    assert monitor.streams[disk_stream].info.state.messages == 1

    await publish_messages(monitor.js, subject_from_stream_name(memory_stream), 1)
    await publish_messages(monitor.js, subject_from_stream_name(disk_stream), 1)

    # Should move memory stream messages to disk stream since we set memory use to 100%
    storage_manager.running = True  # reset the manager to 'running' so it actually does things
    await run_storage_manager_loop(storage_manager)
    await monitor.refresh_stats()
    assert monitor.streams[memory_stream].info.state.messages == 0
    assert monitor.streams[disk_stream].info.state.messages == 4
