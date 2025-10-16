import json
from pathlib import Path
from huntsman.pocs.nats.memory_monitor import monitor_memory


def test_monitor_memory_sleep_called(mocker, tmp_path):
    """Test that the sleep function is called the appropriate amount of times
    and for the appropriate length of time"""
    fake_mem = mocker.Mock()
    fake_mem.percent = 85.0
    mocker.patch("huntsman.pocs.nats.memory_monitor.psutil.virtual_memory", return_value=fake_mem)

    mock_sleep = mocker.patch("huntsman.pocs.nats.memory_monitor.time.sleep")

    monitor_memory(
        memory_threshold=70,
        check_interval=1,
        iterations=2,
        memory_status_file=str(tmp_path / "status.json"),
    )

    mock_sleep.assert_called_once_with(1)


def test_monitor_memory_invalid_threshold(mocker, tmp_path):
    """Tests that an invalid input threshold is handled"""
    fake_mem = mocker.Mock()
    fake_mem.percent = 85.0
    mocker.patch("huntsman.pocs.nats.memory_monitor.psutil.virtual_memory", return_value=fake_mem)

    status_path = str(tmp_path / "status.json")

    monitor_memory(
        memory_threshold=9001,  # Invalid, should go to 31
        check_interval=1,
        iterations=2,
        memory_status_file=str(tmp_path / "status.json"),
    )

    # Verify file content
    data = json.loads(Path(status_path).read_text())
    assert data["memory_used_percent"] == 85.0
    assert data["should_pause"] is True
    assert data["threshold"] == 31


def test_monitor_memory_high_usage(mocker, tmp_path):
    """Tests that high memory usage is handled"""
    fake_mem = mocker.Mock()
    fake_mem.percent = 85.0
    mocker.patch("huntsman.pocs.nats.memory_monitor.psutil.virtual_memory", return_value=fake_mem)
    fake_time = 1234567890.0
    mocker.patch(
        "huntsman.pocs.nats.memory_monitor.time.time",
        return_value=fake_time
    )

    status_path = str(tmp_path / "status.json")

    # Run one iteration only
    monitor_memory(
        memory_threshold=50,
        check_interval=0.01,
        memory_status_file=status_path,
        iterations=1,
    )

    # Verify file content
    data = json.loads(Path(status_path).read_text())
    assert data["memory_used_percent"] == 85.0
    assert data["should_pause"] is True
    assert data["threshold"] == 50
    assert data["timestamp"] == fake_time


def test_monitor_memory_low_usage(mocker, tmp_path):
    """Test that low memory usage is handled"""
    fake_mem = mocker.Mock()
    fake_mem.percent = 20.0
    mocker.patch("huntsman.pocs.nats.memory_monitor.psutil.virtual_memory", return_value=fake_mem)
    fake_time = 1234567890.0
    mocker.patch(
        "huntsman.pocs.nats.memory_monitor.time.time",
        return_value=fake_time
    )

    status_path = str(tmp_path / "status.json")

    monitor_memory(
        memory_threshold=50,
        check_interval=0.01,
        memory_status_file=status_path,
        iterations=1,
    )

    data = json.loads(Path(status_path).read_text())
    assert data["memory_used_percent"] == 20
    assert data["should_pause"] is False
    assert data["threshold"] == 50
    assert data["timestamp"] == fake_time
