import asyncio
import os
from nats.js.api import StreamConfig
import pytest
import pytest_asyncio
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Tuple

from nats.js import JetStreamContext

from huntsman.pocs.nats.streams import MemoryStreamConfig, DiskStreamConfig, start_streams, delete_streams
from huntsman.pocs.nats.monitor import HuntsmanMonitor
from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig
from huntsman.pocs.nats.utils import list_streams, subject_from_stream_name


@pytest.fixture
def tmp_memory_file():
    tmp = NamedTemporaryFile(delete=False)
    yield tmp.name
    os.remove(tmp.name)


@pytest.fixture
def stream_configs() -> Tuple[MemoryStreamConfig, DiskStreamConfig]:
    mem = MemoryStreamConfig(max_bytes=1024)
    # Use workqueue for easier testing
    disk = DiskStreamConfig(max_bytes=1024, retention="workqueue")
    return mem, disk


@pytest_asyncio.fixture
async def setup_streams(js: JetStreamContext):
    """Fixture that creates memory/disk streams and cleans them up."""
    mem_cfg = MemoryStreamConfig(max_bytes=10000)
    disk_cfg = DiskStreamConfig(max_bytes=10000)
    yield await start_streams(js, 1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    await delete_streams(js)


async def publish_messages(js: JetStreamContext, subject: str, n: int):
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())
        print(f"Published to subject: {subject}")


@pytest.fixture
def monitor(js, tmp_memory_file):
    output_file = NamedTemporaryFile(delete=False).name
    yield HuntsmanMonitor(js, memory_status_file=tmp_memory_file, output_file=output_file)
    os.remove(output_file)


@pytest.mark.asyncio
async def test_monitor_stream_activation(js: JetStreamContext,  monitor: HuntsmanMonitor):
    """Tests that new streams are added to the monitor when as they are created"""
    await monitor.refresh_stats()
    assert len(monitor.streams) == 0  # no streams exist yet

    try:
        await js.add_stream(StreamConfig(name="memory_0", subjects=["memory_0.>"], retention="workqueue"))
        await js.add_stream(StreamConfig(name="disk_0", subjects=["disk_0.>"], retention="workqueue"))

        await monitor.refresh_stats()
        assert len(monitor.streams) == 2  # streams should be picked up
    finally:
        await js.delete_stream("memory_0")
        await js.delete_stream("disk_0")


@pytest.mark.asyncio
async def test_monitor_stream_deactivation(js: JetStreamContext,  monitor: HuntsmanMonitor, stream_configs):
    """Tests that streams are not counted towards stats when they are destroyed"""
    mem_cfg, disk_cfg = stream_configs
    mem_streams, disk_streams = await start_streams(js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    memory_stream = mem_streams[0].config.name
    disk_stream = disk_streams[0].config.name

    await monitor.refresh_stats()
    assert len(monitor.streams) == 2  # one memory, one disk stream

    await publish_messages(js, subject_from_stream_name(memory_stream), 1)
    await publish_messages(js, subject_from_stream_name(disk_stream), 1)
    await js.delete_stream(disk_stream)
    await monitor.refresh_stats()

    assert len(monitor.streams) == 2  # Should be the same still
    assert monitor.streams[memory_stream].info.state.messages == 1
    assert monitor.streams[disk_stream].info.state.messages == 0
    assert monitor.streams[memory_stream].active == True
    assert monitor.streams[disk_stream].active == False

    # The stats should be only represented by the remaining memory stream
    assert monitor.stats.total_disk_bytes == 0
    assert monitor.stats.total_disk_messages == 0
    assert monitor.stats.total_messages == monitor.stats.total_memory_messages
    assert monitor.stats.total_bytes == monitor.stats.total_memory_bytes

    # Delete streams and ensure they're gone
    await delete_streams(js)
    streams = await js.streams_info()
    assert len(streams) == 0


@pytest.mark.asyncio
async def test_monitor_rates(js: JetStreamContext, monitor: HuntsmanMonitor, stream_configs):
    """Test that the monitor calculates the produced and consumed rates."""
    mem_cfg, disk_cfg = stream_configs
    try:
        mem_streams, _ = await start_streams(js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
        memory_stream = mem_streams[0].config.name

        # # Refresh the monitor stats to get initial state
        await monitor.refresh_stats()
        assert len(monitor.streams) == 2  # one memory, one disk stream

        subject = subject_from_stream_name(memory_stream)
        await publish_messages(js, subject, 10)

        # Refresh. Messages have been produced but not consumed
        await monitor.refresh_stats()
        assert monitor.streams[memory_stream].produced_rate > 0
        assert monitor.streams[memory_stream].consumed_rate <= 0

        # Consume the messages
        consumer = Consumer(ConsumerConfig(TemporaryDirectory().name), js, "1")
        subscription = await js.pull_subscribe(subject, durable="1")
        task = asyncio.create_task(consumer.run_consumer(memory_sub=subscription))
        await asyncio.sleep(1)  # Wait for streams to be consumed
        await consumer.shutdown()
        await asyncio.wait_for(task, timeout=2)

        # sub = await js.pull_subscribe(subject)
        # msgs = await sub.fetch(10)
        # for msg in msgs:
        #     await msg.ack()
        # await asyncio.sleep(1)

        # Messages have been consumed but not produced
        await monitor.refresh_stats()
        assert monitor.streams[memory_stream].produced_rate <= 0
        assert monitor.streams[memory_stream].consumed_rate > 0
    finally:
        await delete_streams(js)
        mem, disk = await list_streams(js)
        assert len(mem) == 0
        assert len(disk) == 0
