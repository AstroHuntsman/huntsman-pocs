import asyncio
import argparse
import signal

import nats

from huntsman.pocs.nats.consumer import ConsumerConfig, Consumer


async def run_consumers(cfg: ConsumerConfig, nats_server: str, n_consumers: int):
    print(f"Starting {n_consumers} NATS consumers...")

    nc = None
    stop_event = asyncio.Event()

    try:
        print(f"Connecting to NATS server at {nats_server}")
        nc = await nats.connect(servers=[nats_server])
        js = nc.jetstream()

        consumers = []
        for i in range(n_consumers):
            consumers.append(Consumer(cfg, js, str(i+1)))

        # Set up the shutdown on interrupt signals
        def shutdown():
            for c in consumers:
                asyncio.create_task(c.shutdown())
            stop_event.set()  # Interrupt event

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, shutdown)
        loop.add_signal_handler(signal.SIGTERM, shutdown)

        tasks = []
        for consumer in consumers:
            tasks.append(asyncio.create_task(consumer.run_consumer()))

        await stop_event.wait()  # Wait for interrupt event
    finally:
        if nc:
            print("Closing NATS connection...")
            await nc.close()
        print("Done")


if __name__ == "__main__":
    cfg = ConsumerConfig()
    parser = argparse.ArgumentParser(
        description="Setup and run NATS Jetstream consumers. Requires streams to have been started already.")
    setup_args = parser.add_argument_group(title="Setup configuration")
    setup_args.add_argument("-n", "--num-consumers", type=int, required=True,
                            help="The number of consumers to start")
    setup_args.add_argument("-s", "--nats-server", type=str,
                            default="nats://localhost:4222", help="The nats server host and port.")

    consumer_args = parser.add_argument_group(title="Consumer Config")
    consumer_args.add_argument("-o", "--consumer_output_dir", type=str,
                               default=cfg.consumer_output_dir, help="The directory to ouptut consumer data to")
    consumer_args.add_argument("-c", "--compression-method", type=str,
                               default=cfg.compression_method, help="The compression method to use.")
    consumer_args.add_argument("-d", "--disable-file-writing", action="store_true",
                               default=cfg.disable_file_writing, help="Whether to disable file writing for this consumer.")
    consumer_args.add_argument("-w", "--num-writer-threads", type=int,
                               default=cfg.num_writer_threads, help="Number of threads to use when writing to file.")
    args = parser.parse_args()
    cfg = ConsumerConfig(consumer_output_dir=args.consumer_output_dir, compression_method=args.compression_method,
                         disable_file_writing=args.disable_file_writing, num_writer_threads=args.num_writer_threads)
    asyncio.run(run_consumers(cfg, args.nats_server, args.num_consumers))
