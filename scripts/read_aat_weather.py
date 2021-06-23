import sys
import time
import requests

from panoptes.utils.database.file import PanFileDB
from panoptes.utils.serializers import from_yaml
from huntsman.pocs.utils.safety import get_aat_weather, AAT_URL, AAT_COLUMNS


def main(read_delay=60,
         store_result=False,
         storage_name='weather-AAT',
         storage_dir='.',
         verbose=False,
         **kwargs):

    db = PanFileDB(storage_dir=storage_dir)

    while True:
        try:
            data = get_aat_weather()
            if verbose:
                print(f'{data!r}')
            db.insert_current(storage_name, data, store_permanently=store_result)
            time.sleep(read_delay)
        except KeyboardInterrupt:
            print(f'Cancelled by user, shutting down AAT monitor.')
            break


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Fetch the AAT weather data")
    parser.add_argument('--store-result', default=False, action='store_true',
                        help='If data entries should be saved to db, default False.')
    parser.add_argument('--storage-name', default='weather-AAT',
                        help='Name of collection for storing results.')
    parser.add_argument('--storage-dir', default='.',
                        help='Directory for storing results, default current dir.')
    parser.add_argument('--read-delay', default=60, type=int,
                        help='Number of seconds between reads.')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='Output data on the command line.')

    args = parser.parse_args()

    main(**vars(args))
