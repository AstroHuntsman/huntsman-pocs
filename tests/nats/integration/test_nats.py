import nats
import pytest
import pytest_asyncio

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig, ConsumerStats


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
