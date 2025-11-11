import asyncio
import pytest
from tempfile import TemporaryDirectory

from nats.js import JetStreamContext
from nats.js.api import StreamConfig

from huntsman.pocs.nats.streams import start_streams, delete_streams
from huntsman.pocs.nats.monitor import HuntsmanMonitor
from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig
from huntsman.pocs.nats.utils import subject_from_stream_name


async def publish_messages(js: JetStreamContext, subject: str, n: int):
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())
        print(f"Published to subject: {subject}")


@pytest.mark.asyncio
async def test_monitor_stream_activation(monitor: HuntsmanMonitor):
    """Tests that new streams are added to the monitor when as they are created"""
    await monitor.refresh_stats()
    assert len(monitor.streams) == 0  # no streams exist yet

    await monitor.js.add_stream(StreamConfig(name="memory_0", subjects=["memory_0.>"], retention="workqueue"))
    await monitor.js.add_stream(StreamConfig(name="disk_0", subjects=["disk_0.>"], retention="workqueue"))

    await monitor.refresh_stats()
    assert len(monitor.streams) == 2  # streams should be picked up


@pytest.mark.asyncio
async def test_monitor_stream_deactivation(monitor: HuntsmanMonitor, stream_configs):
    """Tests that streams are not counted towards stats when they are destroyed"""
    mem_cfg, disk_cfg = stream_configs
    mem_streams, disk_streams = await start_streams(monitor.js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    memory_stream = mem_streams[0].config.name
    disk_stream = disk_streams[0].config.name

    await monitor.refresh_stats()
    assert len(monitor.streams) == 2  # one memory, one disk stream

    await publish_messages(monitor.js, subject_from_stream_name(memory_stream), 1)
    await publish_messages(monitor.js, subject_from_stream_name(disk_stream), 1)
    await monitor.js.delete_stream(disk_stream)
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
    await delete_streams(monitor.js)
    streams = await monitor.js.streams_info()
    assert len(streams) == 0


@pytest.mark.asyncio
async def test_monitor_rates(monitor: HuntsmanMonitor, stream_configs):
    """Test that the monitor calculates the produced and consumed rates."""
    mem_cfg, disk_cfg = stream_configs
    mem_streams, disk_streams = await start_streams(monitor.js, num_streams=1, mem_cfg=mem_cfg, disk_cfg=disk_cfg)
    memory_stream = mem_streams[0].config.name
    disk_stream = disk_streams[0].config.name

    # Refresh the monitor stats to get initial state
    await monitor.refresh_stats()
    assert len(monitor.streams) == 2  # one memory, one disk stream

    mem_subject = subject_from_stream_name(memory_stream)
    disk_subject = subject_from_stream_name(disk_stream)
    await publish_messages(monitor.js, mem_subject, 10)
    await publish_messages(monitor.js, disk_subject, 10)

    # Refresh. Messages have been produced but not consumed
    await monitor.refresh_stats()
    assert monitor.streams[memory_stream].produced_rate > 0
    assert monitor.streams[memory_stream].consumed_rate <= 0
    assert monitor.streams[disk_stream].produced_rate > 0
    assert monitor.streams[disk_stream].consumed_rate <= 0

    # Consume the messages
    consumer = Consumer(ConsumerConfig(TemporaryDirectory().name), monitor.js, "1")
    mem_subscription = await monitor.js.pull_subscribe(mem_subject, durable="1")
    disk_subscription = await monitor.js.pull_subscribe(disk_subject, durable="1")
    task = asyncio.create_task(consumer.run_consumer(
        memory_sub=mem_subscription, disk_sub=disk_subscription))
    await asyncio.sleep(2)  # Wait for streams to be consumed
    await consumer.shutdown()
    await asyncio.wait_for(task, timeout=5)

    # Messages have been consumed but not produced
    await monitor.refresh_stats()
    assert monitor.streams[memory_stream].produced_rate <= 0
    assert monitor.streams[memory_stream].consumed_rate > 0
    assert monitor.streams[disk_stream].produced_rate <= 0
    assert monitor.streams[disk_stream].consumed_rate > 0
