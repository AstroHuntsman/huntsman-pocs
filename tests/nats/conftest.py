import pytest
import asyncio
import docker
import time
import pytest_asyncio
from typing import AsyncGenerator

import nats
from nats.js import JetStreamContext


@pytest.fixture(scope="session")
def nats_server():
    """
    Fixture to start a NATS server in a Docker container.
    """
    client = docker.from_env()
    container = client.containers.run(
        "nats:latest",
        ports={"4222/tcp": 4222},
        detach=True,
        command="-js",
    )
    # Wait for the server to start
    time.sleep(2)
    yield "nats://localhost:4222"
    container.stop()
    container.remove()

@pytest.fixture(scope="session")
def nats_addr(nats_server):
    return nats_server

@pytest_asyncio.fixture
async def js(nats_addr) -> AsyncGenerator[JetStreamContext, None]:
    """Fixture to connect to NATS and return JetStream context."""
    nc = await nats.connect(nats_addr)
    yield nc.jetstream()
    await nc.close()