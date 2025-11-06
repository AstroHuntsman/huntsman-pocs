import os
import pytest
from tempfile import NamedTemporaryFile
from typing import Tuple, Generator

from nats.js import JetStreamContext

from huntsman.pocs.nats.streams import MemoryStreamConfig, DiskStreamConfig
from huntsman.pocs.nats.storage_manager import StorageManager, StorageManagerConfig
from huntsman.pocs.nats.monitor import HuntsmanMonitor


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


@pytest.fixture
def monitor(js: JetStreamContext, tmp_memory_file: str) -> Generator[HuntsmanMonitor, None, None]:
    output_file = NamedTemporaryFile(delete=False).name
    yield HuntsmanMonitor(js, memory_status_file=tmp_memory_file, output_file=output_file)
    os.remove(output_file)


@pytest.fixture(scope="function")
def storage_manager(js, tmp_memory_file) -> StorageManager:
    cfg = StorageManagerConfig(
        memory_threshold=50, memory_status_file=tmp_memory_file, check_interval=0.1)
    return StorageManager(cfg, js)
