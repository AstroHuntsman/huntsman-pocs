import argparse
import asyncio
import signal

import nats

from huntsman.pocs.nats.storage_manager import StorageManager, StorageManagerConfig


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
    args = parser.parse_args()
    cfg = StorageManagerConfig(**vars(args))
    asyncio.run(main(cfg))
