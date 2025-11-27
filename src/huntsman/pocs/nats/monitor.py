import asyncio
import os
from dataclasses import dataclass, asdict
import json
import time
from typing import Dict, Literal, List, Optional
import psutil
from tempfile import NamedTemporaryFile

from nats.js import JetStreamContext
from nats.js.api import StreamInfo, ConsumerInfo

from huntsman.pocs.nats.utils import get_memory_usage, update_memory_usage, list_streams


class HuntsmanStreamStats():
    """The same as the JS StreamInfo Object, but keeps track of produce/consume rates
    and sets the stream type explicitly"""

    def __init__(self, init_info: StreamInfo, init_consumers: List[ConsumerInfo], stream_type: Literal["memory", "disk"], init_time: Optional[float] = None):
        self.active = True
        self.info = init_info
        self.consumers = init_consumers
        self.stream_type = stream_type
        self._last_timestamp = init_time
        if not self._last_timestamp:
            self._last_timestamp = time.time()

        self.produced_rate: int = 0
        self.consumed_rate: int = 0

        self._last_message_count: int = 0
        self._last_delivered_count: Dict[str, int] = {}

    @property
    def time_delta(self) -> float:
        return time.time() - self._last_timestamp

    async def refresh(self, js: JetStreamContext):
        try:
            self.info = await js.stream_info(self.info.config.name)
        except Exception as e:
            print(f"Error fetching stream info: {e}")
            return
        self.consumers = await js.consumers_info(self.info.config.name)
        self._calculate_throughput(new_timestamp=time.time())

    def _calculate_throughput(self, new_timestamp: float):
        """Update the stream stats and recalc produced/consumed rates.
        Args:
            new_timestamp: The new timestamp to use for statistics calculation
        """
        time_delta = new_timestamp - self._last_timestamp
        if time_delta <= 0:
            print(
                f"Invalid timestamps: Δt={time_delta:.4f}s (new={new_timestamp}, last={self._last_timestamp}). Skipping update.")
            return

        # Produced rate
        produced_delta = self.info.state.messages - self._last_message_count
        if produced_delta < 0:  # handle reset/cleanup
            produced_delta = self.info.state.messages
        self.produced_rate = produced_delta / time_delta

        # Consumed rate
        consumed = 0
        for consumer in self.consumers:
            last_deliv = self._last_delivered_count.get(consumer.name, 0)
            consumed += max(0, consumer.delivered.stream_seq - last_deliv)
        self.consumed_rate = consumed / time_delta

        # Update internal state
        self._last_message_count = self.info.state.messages
        self._last_delivered_count = {c.name: c.delivered.stream_seq for c in self.consumers}
        self._last_timestamp = new_timestamp

    def to_dict(self):
        return {
            "active": self.active,
            "name": self.info.config.name,
            "type": self.stream_type,
            "messages": self.info.state.messages,
            "bytes": self.info.state.bytes,
            "produced_rate": self.produced_rate,
            "consumed_rate": self.consumed_rate,
        }


@dataclass
class SummaryStats:
    total_messages: int = 0
    total_memory_messages: int = 0
    total_disk_messages: int = 0
    total_bytes: int = 0
    total_memory_bytes: int = 0
    total_disk_bytes: int = 0
    total_produced_rate: float = 0
    total_consumed_rate: float = 0
    memory_usage: float = 0
    timestamp: float = 0


class HuntsmanMonitor:

    def __init__(self, js: JetStreamContext, memory_status_file: str, output_file: Optional[str] = None):
        """Class for state-management of JetStreamContext statistics for the Huntsman setup
        Args:
            js: The JetStream context object to retrieve and track the stats for
            memory_status_file: The location of the memory status file that holds the memory usage data
            output_file: The filepath to output stats to. If not supplied, will create a temporary file upon writing.
        """
        self.js = js
        self.streams: Dict[str, HuntsmanStreamStats] = {}
        self.stats = SummaryStats()
        self.memory_status_file = memory_status_file
        self.output_file = output_file
        if not output_file:
            self.output_file = NamedTemporaryFile(delete=False).name

    async def init_streams(self):
        """Grabs the stream information from the JS context"""
        print("Initialising streams...")
        await self._index_streams()  # Update all active streams
        await self._update_streams()  # Initialise stats by running update on each object

    async def refresh_stats(self):
        """Updates the JsStats object by refreshing the StreamStats and SummaryStats objects"""
        if self.streams == {}:
            await self.init_streams()

        # Reindex active streams
        await self._index_streams()

        # Update each stream's stats
        await self._update_streams()

        # Update totals, memory usage and timestamp
        self.stats.timestamp = time.time()
        await update_memory_usage(self.memory_status_file, psutil.virtual_memory().percent, self.stats.timestamp)
        self.stats.memory_usage, _ = await get_memory_usage(self.memory_status_file)

        self.stats.total_memory_messages = 0
        self.stats.total_disk_messages = 0
        self.stats.total_memory_bytes = 0
        self.stats.total_disk_bytes = 0
        self.stats.total_produced_rate = 0
        self.stats.total_consumed_rate = 0
        for name in self._get_active_streams():
            stream = self.streams[name]
            if stream.stream_type == "memory":
                self.stats.total_memory_messages += stream.info.state.messages
                self.stats.total_memory_bytes += stream.info.state.bytes
            else:
                self.stats.total_disk_messages += stream.info.state.messages
                self.stats.total_disk_bytes += stream.info.state.bytes
            self.stats.total_produced_rate += stream.produced_rate
            self.stats.total_consumed_rate += stream.consumed_rate

        self.stats.total_messages = self.stats.total_memory_messages + self.stats.total_disk_messages
        self.stats.total_bytes = self.stats.total_memory_bytes + self.stats.total_disk_bytes

    async def _index_streams(self):
        """Updates the tracked streams by finding all memory and disk streams currently active in the Jetstream
        context. Will remove any tracked streams that are not in the context anymore.
        """
        currently_active = self._get_active_streams()

        # Add untracked active streams
        memory_streams, disk_streams = await list_streams(self.js)
        tasks = []
        for stream_name, stream_type in [(s, "memory") for s in memory_streams] + [(s, "disk") for s in disk_streams]:
            if stream_name not in currently_active:
                tasks.append(self._add_stream(stream_name, stream_type))
        await asyncio.gather(*tasks)

        # Drop stale streams
        for stream_name in currently_active:
            if stream_name not in memory_streams + disk_streams:
                self._deactivate_stream_tracking(stream_name)

    async def _add_stream(self, stream_name, stream_type):
        """Adds a stream to the tracking"""
        print(f"Adding new stream to tracking: {stream_name}")
        try:
            stream_info = await self.js.stream_info(stream_name)
        except Exception as e:
            print(f"Error fetching stream info: {e}")
            return
        consumers = await self.js.consumers_info(stream_name)
        self.streams[stream_info.config.name] = HuntsmanStreamStats(
            init_info=stream_info,
            init_consumers=consumers,
            stream_type=stream_type,
        )

    def _deactivate_stream_tracking(self, stream_name):
        """Removes a stream from tracking"""
        print(f"Removing old stream from tracking: {stream_name}")
        try:
            self.streams[stream_name].active = False
        except Exception as e:
            print(f"Error removing {stream_name} from tracking: {e}")

    def _get_active_streams(self) -> List[str]:
        """Gets all stream names that are currently actively tracked"""
        active = []
        for name, stream in self.streams.items():
            if stream.active:
                active.append(name)
        return active

    async def _update_streams(self):
        """Updates the stats of every stream being tracked"""
        tasks = [s.refresh(self.js) for s in self.streams.values() if s.active]
        await asyncio.gather(*tasks)

    def save_stats_to_file(self):
        """Save all stats to a file in .json format"""
        directory = os.path.dirname(self.output_file)
        if directory:
            os.makedirs(directory, exist_ok=True)  # Make dir if doesn't exist
        try:
            with open(self.output_file, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Error writing stats to file: {e}")

    def to_dict(self):
        """Dumps the Summary and all StreamStats to a dictionary"""
        _dict = {"summary_stats": asdict(self.stats), "streams": {}}
        for name, stream in self.streams.items():
            _dict["streams"][name] = stream.to_dict()
        return _dict

    async def print_stats(self):
        """Print all stats for active streams to stdout"""
        print("\n---------- Stream Statistics Summary ----------")
        print(f"Memory Usage: {self.stats.memory_usage:.2f}%")
        print(
            f"Total Messages: {self.stats.total_messages} ({self.stats.total_memory_messages} in memory, {self.stats.total_disk_messages} on disk)")
        print(
            f"Production Rate: {self.stats.total_produced_rate:.2f} msgs/sec")
        print(
            f"Consumption Rate: {self.stats.total_consumed_rate:.2f} msgs/sec")
        print(
            f"Total Data: {self.stats.total_bytes / (1024*1024):.2f} MB ({self.stats.total_memory_bytes / (1024*1024):.2f} MB in memory, {self.stats.total_disk_bytes / (1024*1024):.2f} MB on disk)")
        print("\n-----------------------------------------------")
