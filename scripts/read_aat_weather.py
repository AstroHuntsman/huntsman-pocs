import sys
import time
import requests

from panoptes.utils.database.file import PanFileDB
from panoptes.utils.serializers import from_yaml


AAT_URL = 'http://aat-ops.anu.edu.au/met/metdata.dat'
AAT_COLUMNS = ['time',
               'outside_temp',
               'inside_temp',
               'mirror_temp',
               'outside_dewpoint',
               'outside_humidity',
               'pressure',
               'wind_speed_avg',
               'wind_gust_max',
               'wind_direction_avg',
               'dome_state',
               'is_raining',
               'inside_dewpoint',
               'sky_ambient_diff_C',
               'sky_ambient_diff_error',
               'daytime_brightness',
               'rain_detections_past_10minutes',
               'wetness_detections_past_10minutes',
               'rain_since_9am',
               'sqm_brightness',
               ]


def get_aat_weather(aat_url=AAT_URL, response_columns=AAT_COLUMNS):
    """Fetch met weather data from AAO weather station.

    Args:
        aat_url (string, optional): URL to query for weather reading. Defaults to AAT_URL.
        response_columns (list, optional): List of column names that map onto the values contained
        in a succesful reponse. Defaults to AAT_COLUMNS.
    """
    response = requests.get(aat_url)
    # raise an exception if response was not successful
    response.raise_for_status()

    if response.ok:
        date, raw_data, _ = response.content.decode().split('\n')
        data = {name: value for name, value in zip(response_columns, raw_data.split('\t'))}
        data['date'] = date
    else:
        data = None

    return data


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
