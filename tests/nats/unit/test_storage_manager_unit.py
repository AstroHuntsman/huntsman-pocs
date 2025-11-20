import pytest
from unittest.mock import AsyncMock, MagicMock

from huntsman.pocs.nats.storage_manager import StorageManager, StorageManagerConfig


@pytest.fixture
def cfg(tmp_path):
    return StorageManagerConfig(
        memory_threshold=50.0,
        memory_status_file=str(tmp_path / "memory_status.json"),
        check_interval=0.1,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_messages_need_moving_above_threshold(mocker, cfg):
    js = AsyncMock()
    mock_get_usage = mocker.patch(
        "huntsman.pocs.nats.storage_manager.get_memory_usage", new_callable=AsyncMock
    )
    mock_get_usage.return_value = (75.0, 0) # 75% usage, timestamp is '0'

    sm = StorageManager(cfg, js)
    result = await sm._messages_need_moving()

    assert result is True
    mock_get_usage.assert_awaited_once_with(cfg.memory_status_file)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_messages_need_moving_below_threshold(mocker, cfg):
    js = AsyncMock()
    mock_get_usage = mocker.patch(
        "huntsman.pocs.nats.storage_manager.get_memory_usage", new_callable=AsyncMock
    )
    mock_get_usage.return_value = (10.0, 0) # 10% usage, timestamp is '0'

    sm = StorageManager(cfg, js)
    result = await sm._messages_need_moving()

    assert result is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_shutdown_sets_running_false(cfg):
    js = AsyncMock()
    sm = StorageManager(cfg, js)
    assert sm.running
    await sm.shutdown()
    assert not sm.running


@pytest.mark.asyncio
@pytest.mark.unit
async def test_shutdown_twice_no_error(cfg):
    js = AsyncMock()
    sm = StorageManager(cfg, js)
    sm.running = False
    await sm.shutdown()  # Should not raise


@pytest.mark.asyncio
@pytest.mark.unit
async def test_flush_stream_to_disk_no_messages(cfg):
    js = AsyncMock()
    js.stream_info = AsyncMock()
    js.stream_info.return_value.state.messages = 0

    sm = StorageManager(cfg, js)
    await sm._flush_stream_to_disk("memory_0", "disk_0")

    js.stream_info.assert_any_await("memory_0")
    js.stream_info.assert_any_await("disk_0")


@pytest.mark.asyncio
async def test_flush_stream_to_disk_stream_info_error(cfg):
    js = AsyncMock()
    js.stream_info = AsyncMock(side_effect=Exception("Stream not found"))

    sm = StorageManager(cfg, js)
    await sm._flush_stream_to_disk("memory_0", "disk_0")  # Should handle gracefully


@pytest.mark.asyncio
@pytest.mark.unit
async def test_flush_stream_to_disk_success(mocker, cfg):
    js = AsyncMock()
    mock_subject = mocker.patch(
        "huntsman.pocs.nats.storage_manager.subject_from_stream_name", return_value="subj"
    )
    mock_move = mocker.patch(
        "huntsman.pocs.nats.storage_manager.move_messages_to_new_subject", new_callable=AsyncMock
    )

    js.stream_info = AsyncMock()
    js.stream_info.side_effect = [
        MagicMock(state=MagicMock(messages=5)),
        MagicMock(state=MagicMock(messages=10)),
    ]
    js.add_consumer = AsyncMock()
    js.pull_subscribe = AsyncMock(return_value="subscription")
    mock_move.return_value = 5

    sm = StorageManager(cfg, js)
    await sm._flush_stream_to_disk("memory_1", "disk_1", batch_size=50)

    js.add_consumer.assert_awaited_once()
    js.pull_subscribe.assert_awaited_once()
    mock_move.assert_awaited_once()
    mock_subject.assert_any_call("memory_1")
    mock_subject.assert_any_call("disk_1")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_main_loop_triggers_flush(mocker, cfg):
    js = AsyncMock()
    mock_list = mocker.patch(
        "huntsman.pocs.nats.storage_manager.list_streams", new_callable=AsyncMock
    )
    mocker.patch("huntsman.pocs.nats.storage_manager.update_memory_usage")
    mock_get_usage = mocker.patch(
        "huntsman.pocs.nats.storage_manager.get_memory_usage", new_callable=AsyncMock
    )

    mock_list.return_value = (["memory_0"], ["disk_0"])
    mock_get_usage.return_value = (100.0, 0)  # trigger flush

    sm = StorageManager(cfg, js)
    sm._flush_stream_to_disk = AsyncMock()
    sm.running = True

    async def stop_soon(*args, **kwargs):
        sm.running = False
    sm._flush_stream_to_disk.side_effect = stop_soon

    await sm.run()

    mock_list.assert_awaited_once()
    sm._flush_stream_to_disk.assert_awaited_once_with("memory_0", "disk_0")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_raises_if_unequal_streams(mocker, cfg):
    js = AsyncMock()
    mock_list = mocker.patch(
        "huntsman.pocs.nats.storage_manager.list_streams", new_callable=AsyncMock
    )
    mock_list.return_value = (["mem1"], ["disk1", "disk2"])

    sm = StorageManager(cfg, js)
    with pytest.raises(RuntimeError, match="Unequal number of memory"):
        await sm.run()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_raises_if_no_streams(mocker, cfg):
    js = AsyncMock()
    mock_list = mocker.patch(
        "huntsman.pocs.nats.storage_manager.list_streams", new_callable=AsyncMock
    )
    mock_list.return_value = ([], [])

    sm = StorageManager(cfg, js)
    with pytest.raises(RuntimeError, match="No streams available"):
        await sm.run()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_move_messages_to_new_subject_moves_all_messages():
    js = AsyncMock()
    msg1, msg2 = AsyncMock(), AsyncMock()
    msg1.data, msg2.data = b"1", b"2"
    subscription = AsyncMock()
    subscription.fetch = AsyncMock(side_effect=[[msg1, msg2], []])

    from huntsman.pocs.nats.storage_manager import move_messages_to_new_subject
    n = await move_messages_to_new_subject(js, subscription, "new_subject", batch_size=2)

    assert n == 2
    js.publish.assert_any_await("new_subject", b"1")
    js.publish.assert_any_await("new_subject", b"2")
    msg1.ack.assert_awaited_once()
    msg2.ack.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_move_messages_to_new_subject_handles_timeout():
    js = AsyncMock()
    subscription = AsyncMock()
    from nats import errors
    subscription.fetch = AsyncMock(side_effect=errors.TimeoutError())

    from huntsman.pocs.nats.storage_manager import move_messages_to_new_subject
    n = await move_messages_to_new_subject(js, subscription, "new_subject", batch_size=2)
    assert n == 0
