import pytest
from unittest.mock import patch
from typing import Tuple

from nats.js import JetStreamContext

from huntsman.pocs.nats.streams import MemoryStreamConfig, DiskStreamConfig
from huntsman.pocs.nats.storage_manager import StorageManager, move_messages_to_new_subject
from huntsman.pocs.nats.monitor import HuntsmanMonitor
from huntsman.pocs.nats.streams import start_streams
from huntsman.pocs.nats.utils import subject_from_stream_name 


async def publish_messages(js: JetStreamContext, subject: str, n: int):
    """Helper function to publish some dummy messages"""
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())


@pytest.mark.asyncio
async def test_move_messages_to_new_subject(js: JetStreamContext, stream_configs):
    """Test the move_messages_to_new_subject function directly."""
    mem_cfg, _ = stream_configs
    mem_streams, _ = await start_streams(js, num_streams=1, mem_cfg=mem_cfg)
    memory_stream = mem_streams[0].config.name
    memory_subject = subject_from_stream_name(memory_stream)

    # Create a new subject and stream and publish some stuff to it
    new_stream_name = "NEW_STREAM"
    new_subject = "new.subject.>"
    await js.add_stream(name=new_stream_name, subjects=[new_subject])
    await publish_messages(js, memory_subject, 10)
    sub = await js.pull_subscribe(memory_subject, durable="mover")

    # Move messages
    moved_count = await move_messages_to_new_subject(js, sub, new_subject)
    assert moved_count == 10

    # Check that the messages are in the new stream
    new_stream_info = await js.stream_info(new_stream_name)
    assert new_stream_info.state.messages == 10

    # Since the memory stream has "workqueue" retention, messages should be gone
    mem_stream_info = await js.stream_info(memory_stream)
    assert mem_stream_info.state.messages == 0


@pytest.mark.asyncio
async def test_storage_manager_no_messages_to_move(storage_manager: StorageManager, monitor: HuntsmanMonitor, stream_configs):
    """Test that the storage manager does nothing when there are no messages to move."""
    mem_cfg, disk_cfg = stream_configs
    await start_streams(monitor.js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)

    # Set memory usage high to trigger the move
    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.percent = 100
        await monitor.refresh_stats()

    # Run the storage manager
    async def stop_loop(_):
        storage_manager.running = False
    with patch("huntsman.pocs.nats.storage_manager.asyncio.sleep", new=stop_loop):
        await storage_manager.run()

    # Check that no messages were moved
    await monitor.refresh_stats()
    assert monitor.stats.total_messages == 0


@pytest.mark.asyncio
async def test_storage_manager_unequal_streams(storage_manager: StorageManager, stream_configs:Tuple[MemoryStreamConfig, DiskStreamConfig]):
    """Test that the storage manager raises an error with unequal numbers of streams."""
    mem_cfg, disk_cfg = stream_configs

    await start_streams(storage_manager.js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    await storage_manager.js.delete_stream(disk_cfg.name)


    with pytest.raises(RuntimeError):
        await storage_manager.run()
