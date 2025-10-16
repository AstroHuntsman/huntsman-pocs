import nats
import pytest
import pytest_asyncio

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig, ConsumerStats


@pytest_asyncio.fixture
async def consumer(consumer_config, nats_addr):
    """Fixture for a Consumer instance."""
    nc = await nats.connect(nats_addr)
    js = nc.jetstream()
    consumer = Consumer(cfg=consumer_config, js=js, consumer_id="test_consumer")
    yield consumer
    await nc.close()
