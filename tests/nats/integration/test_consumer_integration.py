import asyncio
import pytest
import tempfile
from typing import Tuple
import os
from astropy.io import fits
import numpy as np

from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

from huntsman.pocs.nats.consumer import Consumer, ConsumerConfig
from huntsman.pocs.nats.streams import start_streams
from huntsman.pocs.nats.utils import subject_from_stream_name


@pytest.mark.asyncio
async def test_consumer_startup(nats_env: Tuple[NATS, JetStreamContext]):
    """
    Test that the consumer can start up and connect to NATS.
    """
    config = ConsumerConfig()
    consumer_id = "1"
    nc, js = nats_env
    js = nc.jetstream()

    await start_streams(js, 1)
    consumer = Consumer(config, js, consumer_id)

    # Run the consumer for a short time
    task = asyncio.create_task(consumer.run_consumer())
    await asyncio.sleep(1)
    await consumer.shutdown()
    await asyncio.wait_for(task, timeout=5)

    # Check that the consumer has connected to NATS
    assert nc.is_connected


@pytest.mark.asyncio
async def test_consumer_process_messages(js: JetStreamContext):
    """
    Test that the consumer can process messages and write files to disk.
    """

    await start_streams(js, 1)
    tmpdir = tempfile.TemporaryDirectory().name
    config = ConsumerConfig(consumer_output_dir=tmpdir)
    consumer_id = "1"
    consumer = Consumer(config, js, consumer_id)

    # Start the consumer
    task = asyncio.create_task(consumer.run_consumer())
    await asyncio.sleep(1)

    # Publish a test message
    subject = subject_from_stream_name(f"CAMERA_MEMORY_{consumer_id}")
    data = np.arange(100, dtype=np.uint16).tobytes()
    headers = {"width": "10", "height": "10"}
    await js.publish(subject, data, headers=headers)
    subject = subject_from_stream_name(f"CAMERA_DISK_{consumer_id}")
    await js.publish(subject, data, headers=headers)

    # Run the consumer for a short time
    await asyncio.sleep(2)
    await consumer.shutdown()
    await asyncio.wait_for(task, timeout=5)

    # Check that 2 files have been created - one from memory and one from disk stream
    output_dir = os.path.join(tmpdir, "movie", f"consumer_{consumer_id}")
    files = os.listdir(output_dir)
    assert len(files) == 2

    # Check the content of the file
    for file in files:
        with fits.open(os.path.join(output_dir, file)) as hdul:
            assert hdul[0].data.shape == (10, 10)
            assert np.array_equal(hdul[0].data, np.arange(100).reshape(10, 10))
