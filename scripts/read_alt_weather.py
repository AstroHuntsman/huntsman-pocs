import argparse
import time
import yaml

from panoptes.utils.database.file import PanFileDB
from panoptes.utils.config.client import get_config
from panoptes.utils.library import load_module
from huntsman.pocs.utils.weather import determine_alt_weather_safety
from huntsman.pocs.utils.logger import get_logger


def main(source,
         config,
         store_result,
         storage_dir,
         read_delay,
         verbose,
         **kwargs):
    """Periodically fetch and store weather data from an external weather data source.

    Args:
        source (str): Name of alternative weather data source, must match name in the config.
        config (str or None): Filepath of a config file, if None defaults to config server config.
        store_result (bool): Whether or not weather data should be stored in a permanent database.
        storage_dir (str): Directory in which databases are contained.
        read_delay (int): Delay (in seconds) between weather data readings.
        verbose (bool): Whether to display weather readings to logs.

    Raises:
        ValueError: Will be raised if a config was not loaded via filepath or configserver.
    """
    logger = get_logger()
    db = PanFileDB(storage_dir=storage_dir)

    # if no config file given, default to grabbing config from a config server
    if config is None:
        alt_weather_config = get_config(f'alt_weather_sources.{source}')
    else:
        # for local testing
        with open(config) as f:
            config = yaml.safe_load(f)
            alt_weather_config = config.get('alt_weather_sources').get(source)

    if alt_weather_config is None:
        raise ValueError("The weather source config is None, please supply a config.")

    # load the relevant function for obtaining the weather data
    get_alt_weather_data = load_module('huntsman.pocs.utils.weather.get_' + source)

    while True:
        try:
            # call function for fetching alternate weather data
            data = get_alt_weather_data()
            # determine if the weather data indicates safe conditions
            data = determine_alt_weather_safety(data, alt_weather_config)
            if verbose:
                logger.info(f'{data!r}')
            # insert reading into the source database
            db.insert_current(source, data, store_permanently=store_result)
            time.sleep(read_delay)
        except KeyboardInterrupt:
            logger.info(f'Cancelled by user, shutting down {source} monitor.')
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Fetch the weather data from alternate source.")
    parser.add_argument(
        '--source', default='aat_weather',
        help='Name of weather source and collection for storing results, see `huntsman.yaml`.')
    parser.add_argument('--config', default=None,
                        help='Filepath for the config file, defaults to None.')
    parser.add_argument('--store-result', default=True, action='store_false',
                        help='If data entries should be saved to db, default True.')
    parser.add_argument('--storage-dir', default='/var/huntsman/json_store',
                        help='Directory for storing results, default current dir.')
    parser.add_argument('--read-delay', default=60, type=int,
                        help='Number of seconds between reads.')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='Output data on the command line.')

    args = parser.parse_args()

    main(**vars(args))
