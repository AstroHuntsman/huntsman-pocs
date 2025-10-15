import argparse
import asyncio
from dataclasses import dataclass
import json
import os
import signal
import time
from typing import Dict

import nats
from nats.js import JetStreamContext

from huntsman.pocs.nats.utils import list_streams


@dataclass
class StorageManagerConfig:
    """This class exists to store defaults and synchronise them with the
    StorageManager class and the __main__ argparse arguments"""
    memory_threshold: float = 31.0
    memory_status_file: str = f"images/memory_status.json"
    check_interval: float = 10.0
    nats_stats_file: str = "/tmp/stream_stats.json"


class StorageManager:
    def __init__(self, cfg: StorageManagerConfig, js: JetStreamContext):
        self.cfg = cfg
        self.js = js
        self.lock = asyncio.Lock()
        self.running = True
        self.last_message_counts = {}  # Track previous message counts to calculate rates

    async def run(self):
        # Check streams are present
        self.memory_streams, self.disk_streams = await list_streams(self.js)
        print(f"Found {len(self.memory_streams)} memory streams: {self.memory_streams}")
        print(f"Found {len(self.disk_streams)} disk streams: {self.disk_streams}")
        if not self.memory_streams:
            print("No memory streams found. Please run create_streams.py first.")
        if not self.disk_streams:
            print("No disk streams found. Please run create_streams.py first.")

        # Verify that we have matching pairs
        if len(self.memory_streams) != len(self.disk_streams):
            print(
                f"Warning: Unequal number of memory ({len(self.memory_streams)}) and disk ({len(self.disk_streams)}) streams.")
        if not self.memory_streams or not self.disk_streams:
            raise RuntimeError("No streams available. Exiting. Please run create_streams.")

        # Write initial memory status file if it doesn't exist
        os.makedirs(os.path.dirname(self.cfg.memory_status_file), exist_ok=True)
        if not os.path.exists(self.cfg.memory_status_file):
            async with self.lock:
                with open(self.cfg.memory_status_file, 'w') as f:
                    json.dump({"memory_usage": 0}, f)

        # Main loop
        while self.running:
            await self.check_and_move_messages()
            await asyncio.sleep(self.cfg.check_interval)

    async def shutdown(self):
        if not self.running:
            return  # Prevent double-shutdown
        print("Shutting down tiered storage manager...")
        self.running = False

    async def get_memory_usage(self) -> int:
        """Get current memory usage from status file."""
        try:
            if os.path.exists(self.cfg.memory_status_file):
                async with self.lock:
                    with open(self.cfg.memory_status_file, 'r') as f:
                        memory_data = json.load(f)
                        memory_usage = memory_data.get('memory_usage', 0)
                        return memory_usage
        except Exception as e:
            print(f"Error reading memory status: {e}")

        # Default if file doesn't exist or there's an error
        return 0

    async def get_stream_stats(self) -> Dict[str, any]:
        """Get statistics for all streams."""
        stats = {
            "timestamp": time.time(),
            "memory_usage": await self.get_memory_usage(),
            "streams": {}
        }

        current_counts = {}

        # Process memory streams
        for stream_name in self.memory_streams:
            try:
                stream_info = await self.js.stream_info(stream_name)

                # Get consumer info for this stream
                consumers = []
                try:
                    consumer_info_list = await self.js.consumers_info(stream_name)
                    for consumer in consumer_info_list:
                        consumers.append({
                            "name": consumer.name,
                            "num_pending": consumer.num_pending,
                            "num_ack_pending": consumer.num_ack_pending,
                            "delivered": consumer.delivered.stream_seq,
                            "ack_floor": consumer.ack_floor.stream_seq
                        })
                except Exception as e:
                    print(f"Error getting consumer info for {stream_name}: {e}")

                # Calculate message counts and rates
                messages = stream_info.state.messages
                current_counts[stream_name] = messages

                # Calculate production/consumption rates
                produced_rate = 0
                consumed_rate = 0

                if stream_name in self.last_message_counts:
                    time_diff = stats["timestamp"] - \
                        self.last_message_counts[stream_name]["timestamp"]
                    if time_diff > 0:
                        # Production rate = (current_messages + delivered - last_messages) / time_diff
                        last_messages = self.last_message_counts[stream_name]["count"]
                        produced_delta = messages - last_messages
                        if produced_delta < 0:  # Handle reset/cleanup
                            produced_delta = messages
                        produced_rate = produced_delta / time_diff

                        # Consumption rate estimation based on consumer activity
                        consumed = 0
                        for consumer in consumers:
                            if "last_delivered" in self.last_message_counts[stream_name]:
                                consumed += max(0, consumer["delivered"] - self.last_message_counts[stream_name]
                                                ["last_delivered"].get(consumer["name"], 0))

                        consumed_rate = consumed / time_diff

                # Store last delivered positions for consumers
                last_delivered = {}
                for consumer in consumers:
                    last_delivered[consumer["name"]] = consumer["delivered"]

                stats["streams"][stream_name] = {
                    "type": "memory",
                    "messages": messages,
                    "bytes": stream_info.state.bytes,
                    "first_seq": stream_info.state.first_seq,
                    "last_seq": stream_info.state.last_seq,
                    "consumers": len(consumers),
                    "consumer_details": consumers,
                    "produced_rate": produced_rate,  # messages per second
                    "consumed_rate": consumed_rate   # messages per second
                }

                # Update last message counts
                self.last_message_counts[stream_name] = {
                    "timestamp": stats["timestamp"],
                    "count": messages,
                    "last_delivered": last_delivered
                }

            except Exception as e:
                print(f"Error getting stats for memory stream {stream_name}: {e}")

        # Process disk streams
        for stream_name in self.disk_streams:
            try:
                stream_info = await self.js.stream_info(stream_name)

                # Get consumer info for this stream
                consumers = []
                try:
                    consumer_info_list = await self.js.consumers_info(stream_name)
                    for consumer in consumer_info_list:
                        consumers.append({
                            "name": consumer.name,
                            "num_pending": consumer.num_pending,
                            "num_ack_pending": consumer.num_ack_pending,
                            "delivered": consumer.delivered.stream_seq,
                            "ack_floor": consumer.ack_floor.stream_seq
                        })
                except Exception as e:
                    print(f"Error getting consumer info for {stream_name}: {e}")

                # Calculate message counts and rates
                messages = stream_info.state.messages
                current_counts[stream_name] = messages

                # Calculate production/consumption rates
                produced_rate = 0
                consumed_rate = 0

                if stream_name in self.last_message_counts:
                    time_diff = stats["timestamp"] - \
                        self.last_message_counts[stream_name]["timestamp"]
                    if time_diff > 0:
                        # Production rate = (current_messages + delivered - last_messages) / time_diff
                        last_messages = self.last_message_counts[stream_name]["count"]
                        produced_delta = messages - last_messages
                        if produced_delta < 0:  # Handle reset/cleanup
                            produced_delta = messages
                        produced_rate = produced_delta / time_diff

                        # Consumption rate estimation based on consumer activity
                        consumed = 0
                        for consumer in consumers:
                            if "last_delivered" in self.last_message_counts[stream_name]:
                                consumed += max(0, consumer["delivered"] - self.last_message_counts[stream_name]
                                                ["last_delivered"].get(consumer["name"], 0))

                        consumed_rate = consumed / time_diff

                # Store last delivered positions for consumers
                last_delivered = {}
                for consumer in consumers:
                    last_delivered[consumer["name"]] = consumer["delivered"]

                stats["streams"][stream_name] = {
                    "type": "disk",
                    "messages": messages,
                    "bytes": stream_info.state.bytes,
                    "first_seq": stream_info.state.first_seq,
                    "last_seq": stream_info.state.last_seq,
                    "consumers": len(consumers),
                    "consumer_details": consumers,
                    "produced_rate": produced_rate,  # messages per second
                    "consumed_rate": consumed_rate   # messages per second
                }

                # Update last message counts
                self.last_message_counts[stream_name] = {
                    "timestamp": stats["timestamp"],
                    "count": messages,
                    "last_delivered": last_delivered
                }

            except Exception as e:
                print(f"Error getting stats for disk stream {stream_name}: {e}")

        # Calculate total stats
        total_memory_messages = sum(stats["streams"][name]["messages"]
                                    for name in self.memory_streams if name in stats["streams"])
        total_disk_messages = sum(stats["streams"][name]["messages"]
                                  for name in self.disk_streams if name in stats["streams"])
        total_memory_bytes = sum(stats["streams"][name]["bytes"]
                                 for name in self.memory_streams if name in stats["streams"])
        total_disk_bytes = sum(stats["streams"][name]["bytes"]
                               for name in self.disk_streams if name in stats["streams"])

        total_produced_rate = sum(stats["streams"][name]["produced_rate"] for name in list(
            self.memory_streams) + list(self.disk_streams) if name in stats["streams"])
        total_consumed_rate = sum(stats["streams"][name]["consumed_rate"] for name in list(
            self.memory_streams) + list(self.disk_streams) if name in stats["streams"])

        stats["summary"] = {
            "total_memory_messages": total_memory_messages,
            "total_disk_messages": total_disk_messages,
            "total_messages": total_memory_messages + total_disk_messages,
            "total_memory_bytes": total_memory_bytes,
            "total_disk_bytes": total_disk_bytes,
            "total_bytes": total_memory_bytes + total_disk_bytes,
            "total_produced_rate": total_produced_rate,
            "total_consumed_rate": total_consumed_rate
        }

        # Save stats to file
        try:
            with open(self.cfg.nats_stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
        except Exception as e:
            print(f"Error writing stats to file: {e}")

        # Print summary
        print("\nStream Statistics Summary:")
        print(f"Memory Usage: {stats['memory_usage']:.2f}%")
        print(
            f"Total Messages: {stats['summary']['total_messages']} ({stats['summary']['total_memory_messages']} in memory, {stats['summary']['total_disk_messages']} on disk)")
        print(f"Production Rate: {stats['summary']['total_produced_rate']:.2f} msgs/sec")
        print(f"Consumption Rate: {stats['summary']['total_consumed_rate']:.2f} msgs/sec")
        print(f"Total Data: {stats['summary']['total_bytes'] / (1024*1024):.2f} MB ({stats['summary']['total_memory_bytes'] / (1024*1024):.2f} MB in memory, {stats['summary']['total_disk_bytes'] / (1024*1024):.2f} MB on disk)")

        # Print individual stream stats
        print("\nIndividual Stream Statistics:")
        for stream_name in sorted(stats["streams"].keys()):
            stream = stats["streams"][stream_name]
            print(
                f"{stream_name}: {stream['messages']} messages, {stream['produced_rate']:.2f} msgs/sec produced, {stream['consumed_rate']:.2f} msgs/sec consumed")

        return stats

    async def check_and_move_messages(self):
        """Check memory usage and move messages from memory to disk if needed."""
        try:
            # Get current memory usage
            memory_usage = await self.get_memory_usage()
            print(f"Current memory usage: {memory_usage:.2f}%")

            # Get stream statistics
            await self.get_stream_stats()

            # If memory usage is below threshold, no need to move messages
            if memory_usage < self.cfg.memory_threshold:
                return

            print(
                f"Memory usage {memory_usage:.2f}% exceeds threshold {self.cfg.memory_threshold}%. Moving messages to disk...")

            # Process each pair of streams
            for memory_stream, disk_stream in zip(self.memory_streams, self.disk_streams):
                try:
                    # Get stream info
                    memory_info = await self.js.stream_info(memory_stream)

                    # Only proceed if there are messages to move
                    if memory_info.state.messages == 0:
                        print(f"No messages in {memory_stream} to move.")
                        continue

                    print(f"Moving messages from {memory_stream} to {disk_stream}...")

                    # Get the stream ID index
                    stream_idx = int(memory_stream.split("_")[-1])

                    # Create a consumer to read from memory stream
                    consumer_config = nats.jetstream.ConsumerConfig(
                        durable_name=f"mover_{stream_idx}",
                        ack_policy="explicit",
                        ack_wait=30,  # 30 seconds
                        max_deliver=1
                    )

                    # Create or get the consumer
                    await self.js.add_consumer(memory_stream, consumer_config)

                    # Subscribe to the memory stream
                    sub = await self.js.pull_subscribe(
                        subject=f"camera.memory.{stream_idx}.>",
                        durable=f"mover_{stream_idx}",
                        stream=memory_stream
                    )

                    # Batch process messages
                    total_moved = 0
                    batch_size = 100

                    while True:
                        try:
                            # Fetch a batch of messages
                            msgs = await sub.fetch(batch=batch_size, timeout=1)

                            if not msgs:
                                break

                            # Process each message
                            for msg in msgs:
                                try:
                                    # Extract subject and data
                                    original_subject = msg.subject
                                    data = msg.data

                                    # Transform subject from memory to disk
                                    # Example: camera.memory.0.frame -> camera.archive.0.frame
                                    disk_subject = original_subject.replace("memory", "archive")

                                    # Publish to disk stream
                                    await self.js.publish(disk_subject, data)

                                    # Acknowledge the message from memory stream
                                    await msg.ack()

                                    total_moved += 1
                                except Exception as e:
                                    print(f"Error processing message: {e}")
                                    await msg.nak()  # Negative acknowledgment
                        except Exception as e:
                            if "timeout" not in str(e).lower():
                                print(f"Error fetching messages: {e}")
                            break

                    print(f"Moved {total_moved} messages from {memory_stream} to {disk_stream}")
                except Exception as e:
                    print(f"Error processing stream pair {memory_stream}/{disk_stream}: {e}")
        except Exception as e:
            print(f"Error in check_and_move_messages: {e}")


async def main(nats_server: str, cfg: StorageManagerConfig = StorageManagerConfig()) -> None:
    print(f"Connecting to NATS server at {nats_server}")
    try:
        nc = await nats.connect(servers=[nats_server])
        js = nc.jetstream()
        storage_manager = StorageManager(cfg, js)

        # Set up async signal handlers
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(
            signal.SIGINT, lambda: asyncio.create_task(storage_manager.shutdown()))
        loop.add_signal_handler(
            signal.SIGTERM, lambda: asyncio.create_task(storage_manager.shutdown()))

        print(f"Tiered storage manager started. Checking every {cfg.check_interval} seconds...")
        await storage_manager.run()
    finally:
        if nc:
            await nc.close()

if __name__ == "__main__":
    cfg = StorageManagerConfig()
    parser = argparse.ArgumentParser(description="Runs the NATS storage manager.")
    parser.add_argument("-s", "--nats-server", type=str,
                        default="nats://localhost:4222", help="The nats server host and port.")
    parser.add_argument("-m", "--memory-threshold", type=float,
                        default=cfg.memory_threshold, help="The memory threshold. Once memory usage exceeds this %, will use disk storage. Should be between 0 and 100.")
    parser.add_argument("-f", "--memory-status-file", type=str,
                        default=cfg.memory_status_file, help="The file holding the memory usage status.")
    parser.add_argument("-i", "--check-interval", type=float,
                        default=cfg.check_interval, help="How frequently to check the memory usage (in seconds).")
    parser.add_argument("-n", "--nats-stats-file", type=str,
                        default=cfg.nats_stats_file, help="The file path to dump nats statistics to.")
    args = parser.parse_args()
    cfg = StorageManagerConfig(**vars(args))
    asyncio.run(main(cfg))
