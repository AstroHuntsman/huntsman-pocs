import asyncio
from dataclasses import dataclass
import os

from nats.js import JetStreamContext,  api
from nats import errors

from huntsman.pocs.nats.utils import list_streams, subject_from_stream_name, update_memory_usage, get_memory_usage


@dataclass
class StorageManagerConfig:
    """This class exists to store defaults and synchronise them with the
    StorageManager class and the __main__ argparse arguments"""
    memory_threshold: float = 31.0
    memory_status_file: str = f"images/memory_status.json"
    check_interval: float = 10.0


class StorageManager:
    def __init__(self, cfg: StorageManagerConfig, js: JetStreamContext):
        self.cfg = cfg
        self.js = js
        self.running = True

    async def run(self):
        # Check streams are present
        self.memory_streams, self.disk_streams = await list_streams(self.js)
        print(f"Found {len(self.memory_streams)} memory streams: {self.memory_streams}")
        print(f"Found {len(self.disk_streams)} disk streams: {self.disk_streams}")

        # Verify that we have matching pairs
        if len(self.memory_streams) != len(self.disk_streams):
            raise RuntimeError(
                f"Error: Unequal number of memory ({len(self.memory_streams)}) and disk ({len(self.disk_streams)}) streams.")
        if not self.memory_streams or not self.disk_streams:
            raise RuntimeError("No streams available. Exiting. Please run create_streams.")

        # Write initial memory status file if it doesn't exist
        os.makedirs(os.path.dirname(self.cfg.memory_status_file), exist_ok=True)
        if not os.path.exists(self.cfg.memory_status_file):
            update_memory_usage(self.cfg.memory_status_file, 0)

        # Main loop
        while self.running:
            if await self._messages_need_moving():
                print(f"Memory usage exceeds threshold. Moving messages to disk...")
                tasks = [
                    self._flush_stream_to_disk(mem, disk)
                    for mem, disk in zip(self.memory_streams, self.disk_streams)
                ]
                await asyncio.gather(*tasks)
            await asyncio.sleep(self.cfg.check_interval)

    async def shutdown(self):
        if not self.running:
            return  # Prevent double-shutdown
        print("Shutting down tiered storage manager...")
        self.running = False

    async def _messages_need_moving(self):
        memory_usage, _ = await get_memory_usage(self.cfg.memory_status_file)
        print(f"Current memory usage: {memory_usage:.2f}%")
        # If memory usage is below threshold, no need to move messages
        if memory_usage < self.cfg.memory_threshold:
            return False
        return True

    async def _flush_stream_to_disk(self, memory_stream: str, disk_stream: str, batch_size: int = 100):
        """Check memory usage and move messages from memory to disk if needed.
        The name of the disk stream is inferred from the memory stream.
        Args:
            memory_stream: The name of the memory stream to pull messages from
            disk_stream: The name of the disk stream to push messages to. Note - Jetstream actually pushed to its associated subject
            batch_size: The number of messages to move at a time
        """
        try:
            memory_info = await self.js.stream_info(memory_stream)
            await self.js.stream_info(disk_stream)  # Make sure this exists
        except Exception as e:
            print(f"Could not get stream: {repr(e)}")
            return
        if memory_info.state.messages == 0:
            print(f"No messages in {memory_stream} to move.")
            return
        try:
            print(f"Moving messages from {memory_stream} to {disk_stream}...")
            # Create a consumer to read from memory stream
            stream_idx = int(memory_stream.split("_")[-1])  # Get the stream ID index
            consumer_config = api.ConsumerConfig(
                durable_name=f"mover_{stream_idx}",
                ack_policy="explicit",
                ack_wait=30,  # 30 seconds
                max_deliver=1
            )
            await self.js.add_consumer(memory_stream, consumer_config)

            # Subscribe to the memory stream
            mem_subscription = await self.js.pull_subscribe(
                subject=subject_from_stream_name(memory_stream),
                durable=consumer_config.durable_name,
                stream=memory_stream
            )
            disk_subject = subject_from_stream_name(disk_stream)
            total_moved = await move_messages_to_new_subject(js=self.js, subscription=mem_subscription, subject=disk_subject, batch_size=batch_size)
            print(
                f"Moved {total_moved} messages from {memory_stream} to {disk_stream} subject: {disk_subject}")
        except Exception as e:
            print(f"Error processing stream pair {memory_stream}/{disk_stream}: {e}")


async def move_messages_to_new_subject(js: JetStreamContext, subscription: JetStreamContext.PullSubscription, subject: str, batch_size: int = 100) -> int:
    """Moves all messages from a subscription to a new subject.
    Note - this does not delete messages from the original stream, this cannot be
    done explicitly. In order to guarentee messages are deleted upon consumption,
    the stream must be set up with the "workqueue" retention policy: 
    https://docs.nats.io/nats-concepts/jetstream/streams#retentionpolicy

    Args:
        js: The Jetstream Context
        subscription: The Jetstream subscription to move messages from
        subject: The name of the subject to move the messages to
        batch_size: The maximum number of messages to move at a time
    Return:
        int: The total number of messages moved
    """
    n_moved = 0  # Batch process messages

    while True:
        try:
            # Fetch a batch of messages
            msgs = await subscription.fetch(batch=batch_size, timeout=1)
        except errors.TimeoutError:  # Assume no more messages
            break

        if not msgs:
            break

        # Process each message
        for msg in msgs:
            try:
                # Publish to new subject stream
                await js.publish(subject, msg.data)
                await msg.ack()
                print(f"Moved and acknowledged message")
                n_moved += 1

            except Exception as e:
                print(f"Error processing message: {e}")
                await msg.nak()  # Negative acknowledgment
    return n_moved
