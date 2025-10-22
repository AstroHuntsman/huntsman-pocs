import pytest
import pytest_asyncio
import json
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig

from huntsman.pocs.nats.storage_manager import StorageManager, StorageManagerConfig, move_messages_to_new_subject
from huntsman.pocs.nats.utils import subject_from_stream_name
from tests.nats.conftest import setup_streams, publish_messages


@pytest_asyncio.fixture
async def storage_manager(js: JetStreamContext):
    """Create a StorageManager instance for tests."""
    await setup_streams(js)
    mem_file = NamedTemporaryFile(delete=False)
    stats_file = NamedTemporaryFile(delete=False)
    sm_cfg = StorageManagerConfig(
        memory_threshold=50,
        memory_status_file=mem_file.name,
        check_interval=1,
        nats_stats_file=stats_file.name
    )
    yield StorageManager(cfg=sm_cfg, js=js)
    await js.delete_stream("memory_0")
    await js.delete_stream("disk_0")


@pytest.mark.asyncio
async def test_move_messages_to_new_subject(js: JetStreamContext):
    memory_stream, _ = await setup_streams(js)
    await publish_messages(js, memory_stream, n=2)

    # Create a consumer and subscribe it to the stream
    await js.add_consumer(memory_stream, config=ConsumerConfig(durable_name="mover_0", ack_policy="explicit"))
    sub = await js.pull_subscribe(subject_from_stream_name(memory_stream), durable="mover_0", stream=memory_stream)

    # Assert the state before the function call
    mem_info = await js.stream_info("memory_0")
    disk_info = await js.stream_info("disk_0")
    assert mem_info.state.messages == 2
    assert disk_info.state.messages == 0

    total_moved = await move_messages_to_new_subject(
        js=js,
        subscription=sub,
        subject=subject_from_stream_name("disk_0"),
    )

    assert total_moved == 2
    mem_info = await js.stream_info("memory_0")
    disk_info = await js.stream_info("disk_0")
    assert mem_info.state.messages == 0
    assert disk_info.state.messages == 2


@pytest.mark.asyncio
async def test_messages_need_moving(storage_manager: StorageManager):
    with open(storage_manager.cfg.memory_status_file, "w") as f:
        json.dump({"memory_usage": 60}, f)

    result = await storage_manager._messages_need_moving()
    assert result is True

    with open(storage_manager.cfg.memory_status_file, "w") as f:
        json.dump({"memory_usage": 30}, f)
    result = await storage_manager._messages_need_moving()
    assert result is False


@pytest.mark.asyncio
async def test_flush_stream_to_disk(storage_manager: StorageManager):
    await publish_messages(storage_manager.js, "memory_0", n=3)

    mem_info = await storage_manager.js.stream_info("memory_0")
    assert mem_info.state.messages == 3

    await storage_manager._flush_stream_to_disk("memory_0", "disk_0")

    mem_info = await storage_manager.js.stream_info("memory_0")
    disk_info = await storage_manager.js.stream_info("disk_0")
    print(mem_info.state)
    assert mem_info.state.messages == 0
    assert disk_info.state.messages == 3

    sub = await storage_manager.js.pull_subscribe(subject_from_stream_name("disk_0"), durable="test")
    msgs = await sub.fetch(batch=3, timeout=1)
    data = [msg.data.decode() for msg in msgs]
    assert set(data) == {"msg-0", "msg-1", "msg-2"}


@pytest.mark.asyncio
async def test_shutdown(storage_manager: StorageManager):
    storage_manager.running = True
    await storage_manager.shutdown()
    assert storage_manager.running is False

    # Calling shutdown again should not raise
    await storage_manager.shutdown()
    assert storage_manager.running is False


@pytest.mark.asyncio
async def test_run_single_iteration(storage_manager: StorageManager):
    with open(storage_manager.cfg.memory_status_file, "w") as f:
        json.dump({"memory_usage": 60}, f)
    await publish_messages(storage_manager.js, "memory_0", n=2)
    storage_manager.memory_streams = ["memory_0"]
    storage_manager.disk_streams = ["disk_0"]

    # Patch sleep to stop the loop after one iteration
    async def stop_loop(_):
        storage_manager.running = False
    with patch("asyncio.sleep", new=stop_loop):
        await storage_manager.run()

    mem_info = await storage_manager.js.stream_info("memory_0")
    disk_info = await storage_manager.js.stream_info("disk_0")
    # Messages should have moved
    assert mem_info.state.messages == 0
    assert disk_info.state.messages == 2
