import asyncio
import json
import os
import signal
import sys
import time
import nats
import re

# Configuration
NATS_SERVER = os.environ.get("NATS_SERVER", "nats://localhost:4222")
MEMORY_THRESHOLD = float(os.environ.get("MEMORY_THRESHOLD", "31"))  # Percentage
MEMORY_STATUS_FILE = os.environ.get("MEMORY_STATUS_FILE", "/var/huntsman/images/memory_status.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))  # Seconds between checks
STATS_FILE = os.environ.get("STATS_FILE", "/tmp/stream_stats.json")

# Global variables
running = True
last_message_counts = {}  # Track previous message counts to calculate rates

def signal_handler(sig, frame):
    global running
    print("Shutting down tiered storage manager...")
    running = False

async def list_streams(js):
    """List all streams matching our naming pattern."""
    streams = await js.streams_info()
    memory_streams = []
    disk_streams = []
    
    for stream in streams:
        name = stream.config.name
        if name.startswith("CAMERA_MEMORY_"):
            memory_streams.append(name)
        elif name.startswith("CAMERA_DISK_"):
            disk_streams.append(name)
    
    # Sort streams by their index to match them correctly
    memory_streams.sort(key=lambda x: int(x.split("_")[-1]))
    disk_streams.sort(key=lambda x: int(x.split("_")[-1]))
    
    print(f"Found {len(memory_streams)} memory streams: {memory_streams}")
    print(f"Found {len(disk_streams)} disk streams: {disk_streams}")
    
    return memory_streams, disk_streams

async def setup_streams(js):
    """Ensure all streams exist and are properly configured."""
    memory_streams, disk_streams = await list_streams(js)
    
    if not memory_streams:
        print("No memory streams found. Please run create_streams.py first.")
    
    if not disk_streams:
        print("No disk streams found. Please run create_streams.py first.")
    
    # Verify that we have matching pairs
    if len(memory_streams) != len(disk_streams):
        print(f"Warning: Unequal number of memory ({len(memory_streams)}) and disk ({len(disk_streams)}) streams.")
    
    return memory_streams, disk_streams

async def get_memory_usage():
    """Get current memory usage from status file."""
    try:
        if os.path.exists(MEMORY_STATUS_FILE):
            async with asyncio.Lock():  # Use lock to avoid race conditions
                with open(MEMORY_STATUS_FILE, 'r') as f:
                    memory_data = json.load(f)
                    memory_usage = memory_data.get('memory_usage', 0)
                    return memory_usage
    except Exception as e:
        print(f"Error reading memory status: {e}")
    
    # Default if file doesn't exist or there's an error
    return 0

async def get_stream_stats(js, memory_streams, disk_streams):
    """Get statistics for all streams."""
    global last_message_counts
    stats = {
        "timestamp": time.time(),
        "memory_usage": await get_memory_usage(),
        "streams": {}
    }
    
    current_counts = {}
    
    # Process memory streams
    for stream_name in memory_streams:
        try:
            stream_info = await js.stream_info(stream_name)
            
            # Get consumer info for this stream
            consumers = []
            try:
                consumer_info_list = await js.consumers_info(stream_name)
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
            
            if stream_name in last_message_counts:
                time_diff = stats["timestamp"] - last_message_counts[stream_name]["timestamp"]
                if time_diff > 0:
                    # Production rate = (current_messages + delivered - last_messages) / time_diff
                    last_messages = last_message_counts[stream_name]["count"]
                    produced_delta = messages - last_messages
                    if produced_delta < 0:  # Handle reset/cleanup
                        produced_delta = messages
                    produced_rate = produced_delta / time_diff
                    
                    # Consumption rate estimation based on consumer activity
                    consumed = 0
                    for consumer in consumers:
                        if "last_delivered" in last_message_counts[stream_name]:
                            consumed += max(0, consumer["delivered"] - last_message_counts[stream_name]["last_delivered"].get(consumer["name"], 0))
                    
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
            last_message_counts[stream_name] = {
                "timestamp": stats["timestamp"],
                "count": messages,
                "last_delivered": last_delivered
            }
            
        except Exception as e:
            print(f"Error getting stats for memory stream {stream_name}: {e}")
    
    # Process disk streams
    for stream_name in disk_streams:
        try:
            stream_info = await js.stream_info(stream_name)
            
            # Get consumer info for this stream
            consumers = []
            try:
                consumer_info_list = await js.consumers_info(stream_name)
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
            
            if stream_name in last_message_counts:
                time_diff = stats["timestamp"] - last_message_counts[stream_name]["timestamp"]
                if time_diff > 0:
                    # Production rate = (current_messages + delivered - last_messages) / time_diff
                    last_messages = last_message_counts[stream_name]["count"]
                    produced_delta = messages - last_messages
                    if produced_delta < 0:  # Handle reset/cleanup
                        produced_delta = messages
                    produced_rate = produced_delta / time_diff
                    
                    # Consumption rate estimation based on consumer activity
                    consumed = 0
                    for consumer in consumers:
                        if "last_delivered" in last_message_counts[stream_name]:
                            consumed += max(0, consumer["delivered"] - last_message_counts[stream_name]["last_delivered"].get(consumer["name"], 0))
                    
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
            last_message_counts[stream_name] = {
                "timestamp": stats["timestamp"],
                "count": messages,
                "last_delivered": last_delivered
            }
            
        except Exception as e:
            print(f"Error getting stats for disk stream {stream_name}: {e}")
    
    # Calculate total stats
    total_memory_messages = sum(stats["streams"][name]["messages"] for name in memory_streams if name in stats["streams"])
    total_disk_messages = sum(stats["streams"][name]["messages"] for name in disk_streams if name in stats["streams"])
    total_memory_bytes = sum(stats["streams"][name]["bytes"] for name in memory_streams if name in stats["streams"])
    total_disk_bytes = sum(stats["streams"][name]["bytes"] for name in disk_streams if name in stats["streams"])
    
    total_produced_rate = sum(stats["streams"][name]["produced_rate"] for name in list(memory_streams) + list(disk_streams) if name in stats["streams"])
    total_consumed_rate = sum(stats["streams"][name]["consumed_rate"] for name in list(memory_streams) + list(disk_streams) if name in stats["streams"])
    
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
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        print(f"Error writing stats to file: {e}")
    
    # Print summary
    print("\nStream Statistics Summary:")
    print(f"Memory Usage: {stats['memory_usage']:.2f}%")
    print(f"Total Messages: {stats['summary']['total_messages']} ({stats['summary']['total_memory_messages']} in memory, {stats['summary']['total_disk_messages']} on disk)")
    print(f"Production Rate: {stats['summary']['total_produced_rate']:.2f} msgs/sec")
    print(f"Consumption Rate: {stats['summary']['total_consumed_rate']:.2f} msgs/sec")
    print(f"Total Data: {stats['summary']['total_bytes'] / (1024*1024):.2f} MB ({stats['summary']['total_memory_bytes'] / (1024*1024):.2f} MB in memory, {stats['summary']['total_disk_bytes'] / (1024*1024):.2f} MB on disk)")
    
    # Print individual stream stats
    print("\nIndividual Stream Statistics:")
    for stream_name in sorted(stats["streams"].keys()):
        stream = stats["streams"][stream_name]
        print(f"{stream_name}: {stream['messages']} messages, {stream['produced_rate']:.2f} msgs/sec produced, {stream['consumed_rate']:.2f} msgs/sec consumed")
    
    return stats

async def check_and_move_messages(js, memory_streams, disk_streams):
    """Check memory usage and move messages from memory to disk if needed."""
    try:
        # Get current memory usage
        memory_usage = await get_memory_usage()
        print(f"Current memory usage: {memory_usage:.2f}%")
        
        # Get stream statistics
        await get_stream_stats(js, memory_streams, disk_streams)
        
        # If memory usage is below threshold, no need to move messages
        if memory_usage < MEMORY_THRESHOLD:
            return
        
        print(f"Memory usage {memory_usage:.2f}% exceeds threshold {MEMORY_THRESHOLD}%. Moving messages to disk...")
        
        # Process each pair of streams
        for i, (memory_stream, disk_stream) in enumerate(zip(memory_streams, disk_streams)):
            try:
                # Get stream info
                memory_info = await js.stream_info(memory_stream)
                
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
                await js.add_consumer(memory_stream, consumer_config)
                
                # Subscribe to the memory stream
                sub = await js.pull_subscribe(
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
                                await js.publish(disk_subject, data)
                                
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

async def run():
    # Connect to NATS
    print(f"Connecting to NATS server at {NATS_SERVER}")
    nc = await nats.connect(servers=[NATS_SERVER])
    js = nc.jetstream()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Ensure streams are properly set up
    memory_streams, disk_streams = await setup_streams(js)
    
    if not memory_streams or not disk_streams:
        print("No streams available. Exiting.")
        await nc.close()
        return
    
    print(f"Tiered storage manager started. Checking every {CHECK_INTERVAL} seconds...")
    
    # Write initial memory status file if it doesn't exist
    if not os.path.exists(MEMORY_STATUS_FILE):
        async with asyncio.Lock():
            with open(MEMORY_STATUS_FILE, 'w') as f:
                json.dump({"memory_usage": 0}, f)
    
    # Main loop
    while running:
        await check_and_move_messages(js, memory_streams, disk_streams)
        await asyncio.sleep(CHECK_INTERVAL)
    
    # Clean up
    await nc.close()
    print("Tiered storage manager shutdown complete")

if __name__ == "__main__":
    asyncio.run(run())