import pytest_asyncio
from typing import AsyncGenerator

import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig

from huntsman.pocs.nats.consumer import Consumer


async def setup_streams(js: JetStreamContext):
    """Create memory and disk streams for testing."""
    # use workqueue retention in order to easily check for message acknowledgement
    await js.add_stream(StreamConfig(name="memory_0", subjects=["memory_0.>"], retention="workqueue"))
    await js.add_stream(StreamConfig(name="disk_0", subjects=["disk_0.>"], retention="workqueue"))
    return ("memory_0", "disk_0")


async def publish_messages(js: JetStreamContext, stream_name: str, n: int):
    subject = f"{stream_name}.frame"
    for i in range(n):
        await js.publish(subject, f"msg-{i}".encode())
        print(f"Published to subject: {subject}")


@pytest_asyncio.fixture
async def js(nats_addr) -> AsyncGenerator[JetStreamContext, None]:
    """Fixture to connect to NATS and return JetStream context."""
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
