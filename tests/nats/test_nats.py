import nats
import pytest
import pytest_asyncio

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig, ConsumerStats


@pytest_asyncio.fixture
async def js(nats_addr):
    """Fixture for a Consumer instance."""
    nc = await nats.connect(nats_addr)
    yield nc.jetstream()
    await nc.close()


@pytest_asyncio.fixture
async def consumer(consumer_config, js):
    """Fixture for a Consumer instance."""
    consumer = Consumer(cfg=consumer_config, js=js, consumer_id="test_consumer")
    try:
        yield consumer
    finally:
        await consumer.shutdown()
