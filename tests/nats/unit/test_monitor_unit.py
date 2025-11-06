import json
import pytest
from unittest.mock import AsyncMock
from huntsman.pocs.nats.monitor import (
    HuntsmanMonitor,
    HuntsmanStreamStats,
)
from nats.js.api import StreamInfo, StreamState, StreamConfig, ConsumerInfo, ConsumerConfig


def create_fake_stream_info(name: str):
    """Generic useless stream info object"""
    state = StreamState(messages=100, bytes=1024, first_seq=0, last_seq=0, consumer_count=0)
    config = StreamConfig(name=name)
    return StreamInfo(config=config, state=state)


@pytest.fixture
def fake_stream_info():
    return create_fake_stream_info(name="memory_1")


@pytest.fixture
def fake_consumer_info():
    return [ConsumerInfo(name="consumer_1", stream_name="memory_stream_1", config=ConsumerConfig(), delivered=50, ack_floor=0, num_pending=0, num_ack_pending=0),
            ConsumerInfo(name="consumer_2", stream_name="memory_stream_1", config=ConsumerConfig(), delivered=50, ack_floor=0, num_pending=0, num_ack_pending=0)]


@pytest.fixture
def mock_js(fake_stream_info, fake_consumer_info):
    js = AsyncMock()
    js.stream_info = AsyncMock(return_value=fake_stream_info)
    js.consumers_info = AsyncMock(return_value=fake_consumer_info)
    return js


@pytest.fixture
def monitor(tmp_path, mock_js):
    mem_file = tmp_path / "memory.json"
    return HuntsmanMonitor(js=mock_js, memory_status_file=str(mem_file))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_huntsman_stream_stats_refresh(mock_js, fake_stream_info: StreamInfo, fake_consumer_info: ConsumerInfo):
    stats = HuntsmanStreamStats(fake_stream_info, fake_consumer_info, "memory")
    await stats.refresh(mock_js)

    # Ensure stream_info and consumers_info were called
    mock_js.stream_info.assert_awaited_with(fake_stream_info.config.name)
    mock_js.consumers_info.assert_awaited_with(fake_stream_info.config.name)

    # Rates should be non-negative
    assert stats.produced_rate >= 0
    assert stats.consumed_rate >= 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_huntsman_stream_stats_to_dict(fake_stream_info, fake_consumer_info):
    stats = HuntsmanStreamStats(fake_stream_info, fake_consumer_info, "memory")
    d = stats.to_dict()
    assert d["active"] is True
    assert d["name"] == fake_stream_info.config.name
    assert d["messages"] == 100
    assert d["bytes"] == 1024


@pytest.mark.asyncio
@pytest.mark.unit
async def test_add_stream(monkeypatch, monitor: HuntsmanMonitor, fake_stream_info: StreamInfo, fake_consumer_info: ConsumerInfo):
    monkeypatch.setattr("huntsman.pocs.nats.monitor.list_streams",
                        AsyncMock(return_value=([fake_stream_info.config.name], [])))
    await monitor.init_streams()

    assert fake_stream_info.config.name in list(monitor.streams.keys())
    s = monitor.streams[fake_stream_info.config.name]
    assert s.active
    assert s.info == fake_stream_info
    assert s.consumers == fake_consumer_info


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deactivate_stream(monkeypatch, monitor, fake_stream_info, fake_consumer_info):
    # Simulate a previously tracked stream
    monitor.streams[fake_stream_info.config.name] = HuntsmanStreamStats(
        fake_stream_info, fake_consumer_info, "memory")
    monkeypatch.setattr("huntsman.pocs.nats.utils.list_streams", AsyncMock(return_value=([], [])))

    await monitor._index_streams()
    assert not monitor.streams[fake_stream_info.config.name].active


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_stats(monkeypatch, monitor, fake_stream_info: StreamInfo):
    monkeypatch.setattr("huntsman.pocs.nats.monitor.list_streams",
                        AsyncMock(return_value=([fake_stream_info.config.name], [])))
    monkeypatch.setattr("huntsman.pocs.nats.monitor.get_memory_usage",
                        AsyncMock(side_effect=[42, 10]))
    monkeypatch.setattr("huntsman.pocs.nats.monitor.update_memory_usage", AsyncMock())

    await monitor.refresh_stats()
    stats = monitor.stats
    assert stats.memory_usage == 42
    assert stats.total_memory_messages == 100
    assert stats.total_messages == 100

    fake_stream_info.state.messages = 5
    await monitor.refresh_stats()
    assert stats.memory_usage == 10
    assert stats.total_memory_messages == 5
    assert stats.total_messages == 5


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_active_streams(monitor, fake_stream_info: StreamInfo, fake_consumer_info):
    monitor.streams[fake_stream_info.config.name] = HuntsmanStreamStats(
        fake_stream_info, fake_consumer_info, "memory")

    active = monitor._get_active_streams()
    assert active == [fake_stream_info.config.name]

    new_fake_stream = create_fake_stream_info("memory_stream_2")
    monitor.streams[new_fake_stream.config.name] = HuntsmanStreamStats(
        new_fake_stream, fake_consumer_info, "disk")
    # Set the other stream to inactive
    monitor.streams[fake_stream_info.config.name].active = False

    active = monitor._get_active_streams()
    assert active == [new_fake_stream.config.name]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_update_streams_only_active(monitor, fake_stream_info, fake_consumer_info):
    # Add two streams, one inactive
    s1 = HuntsmanStreamStats(fake_stream_info, fake_consumer_info, "memory")
    s2 = HuntsmanStreamStats(fake_stream_info, fake_consumer_info, "disk")
    s2.active = False
    monitor.streams["s1"] = s1
    monitor.streams["s2"] = s2

    # Patch js for refresh
    js = AsyncMock()
    s1.refresh = AsyncMock()
    s2.refresh = AsyncMock()

    monitor.js = js
    await monitor._update_streams()
    s1.refresh.assert_awaited()
    s2.refresh.assert_not_called()


@pytest.mark.unit
def test_save_stats_to_file(tmp_path, monitor):
    monitor.output_file = tmp_path / "out.json"
    monitor.stats.total_messages = 123
    monitor.save_stats_to_file()
    data = json.loads(open(monitor.output_file).read())
    assert "summary_stats" in data
    assert data["summary_stats"]["total_messages"] == 123


@pytest.mark.asyncio
@pytest.mark.unit
async def test_print_stats(monkeypatch, monitor, fake_stream_info, fake_consumer_info):
    # Add a stream
    s = HuntsmanStreamStats(fake_stream_info, fake_consumer_info, "memory")
    monitor.streams[fake_stream_info.config.name] = s
    monitor.stats.total_messages = 100
    monitor.stats.total_memory_messages = 100
    monitor.stats.memory_usage = 50

    # Patch print to capture output
    printed = []

    def fake_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    monkeypatch.setattr("builtins.print", fake_print)
    await monitor.print_stats()
    # Confirm the summary header was printed
    assert any("Stream Statistics Summary" in line for line in printed)
