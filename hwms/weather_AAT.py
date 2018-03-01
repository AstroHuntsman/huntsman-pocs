#!/usr/bin/env python3

import logging

import astropy.units as u
from astropy.units import cds
from astropy.table import Table
from astropy.time import Time, TimeISO, TimeDelta
from astropy.utils.data import download_file

from datetime import datetime as dt

from . import load_config
from .weather_abstract import WeatherDataAbstract
from .weather_abstract import get_mongodb


class MixedUpTime(TimeISO):
    """Subclass the astropy.time.TimeISO time format to handle the mixed up
    American style time format that the AAT met system uses.
    """

    name= 'mixed_up_time'
    subfmts = (('date_hms',
                '%m-%d-%Y %H:%M:%S',
                '{mon:02d}-{day:02d}-{year:d} {hour:02d}:{min:02d}:{sec:02d}'),
               ('date_hm',
                '%m-%d-%Y %H:%M',
                '{mon:02d}-{day:02d}-{year:d} {hour:02d}:{min:02d}'),
               ('date',
                '%m-%d-%Y',
                '{mon:02d}-{day:02d}-{year:d}'))

# -----------------------------------------------------------------------------
#   AAT metdata Weather Data Class
# -----------------------------------------------------------------------------
class AATMetData(WeatherDataAbstract):
    """Downloads the AAT weather met data and checks if the weather conditions
    are safe.

    Met data from the AAT is parsed into a table where specific entries are then
    checked with customizable parameters to decide its condition and its safety.
    Information of the met data is then able to be stored in mongodb and sent to
    POCS.

    Attributes:
        self.metdata_cfg: An dict that contains infromation about the met data.
        self.thresholds: An array of the thresholds for weather entries.
        self.logger: Used to create debugging messages.
        self.max_age: Maximum age of met data that is to be retrieved.
    """

    def __init__(self, use_mongo=True):
        # Read configuration
        self.config = load_config()
        self.metdata_cfg = self.config['weather']['aat_metdata']
        self.thresholds = self.metdata_cfg['thresholds']

        super().__init__(use_mongo=use_mongo)

        self.logger = logging.getLogger(name=self.metdata_cfg.get('name'))
        self.logger.setLevel(logging.INFO)

        self.max_age = TimeDelta(self.metdata_cfg.get('max_age', 60.), format='sec')

        self._safety_methods = {'rain_condition':self._get_rain_safety,
                                'wetness_condition':self._get_wetness_safety,
                                'wind_condition':self._get_wind_safety,
                                'gust_condition':self._get_gust_safety,
                                'sky_condition':self._get_cloud_safety}

        self.table_data = None

    def capture(self, use_mongo=False, send_message=False, **kwargs):
        """ Update weather data. """
        self.logger.debug('Updating weather data')

        data = {}

        data['weather_data_name'] = self.metdata_cfg.get('name')
        self.table_data = self.fetch_met_data()

        col_names = self.metdata_cfg.get('column_names')

        for name in col_names.keys():
            data[name] = self.table_data[name][0]

        self.weather_entries = data

        return super().capture(use_mongo=False, send_message=False, **kwargs)

    def fetch_met_data(self):
        """Fetches the AAT met data and parses it through a table

        Returns:
            Table of the AAT met data including the entries corresponding units.
        """
        try:
            time_factor = 84600 * u.seconds
            cache_age = Time.now() - self._met_data['time_UTC'][0] * time_factor
        except AttributeError:
            cache_age = 61. * u.second

        if cache_age > self.max_age:
            # Download met data file
            metdata_link = self.metdata_cfg.get('link')
            metdata_file = download_file(metdata_link)
            m = open(metdata_file).read()

            met = m.replace('."\n',' ')
            met = met.replace('" ', '')

            col_names = self.metdata_cfg.get('column_names')

            # Parse the tab delimited met data into a Table
            t = Table.read(met, format='ascii.no_header', delimiter='\t',
                                names=col_names.keys())

            # Convert time strings to Time
            t['time_UTC'] = Time(t['time_UTC'], format='mixed_up_time')
            # Change string format to ISO
            t['time_UTC'].format = 'iso'
            # Convert from AAT standard time to UTC
            t['time_UTC'] = t['time_UTC'] - 10 * u.hour

            # Set units for items that have them
            for name, unit in col_names.items():
                t[name].unit = unit

            self._met_data = t

        return self._met_data

    def _get_rain_safety(self, statuses):
        """Gets the rain safety and weather conditions

        Args:
            statuses: The status of the weather data.

        Returns:
            The rain condition and the rain safety. For example:

                'No data', False
        """

        rain_sensor = statuses['rain_sensor']
        rain_flag = statuses['boltwood_rain_flag']

        if rain_sensor == 'No data' or rain_flag == 'No data':
            rain_condition = 'No data'
            rain_safe = False
        elif rain_sensor == 'Rain' or rain_flag == 'Rain':
            rain_condition = 'Rain'
            rain_safe = False
        elif rain_sensor == 'Invalid' or rain_flag == 'Invalid':
            rain_condition = 'Invalid'
            rain_safe = False
        elif rain_sensor == 'No rain' or rain_flag == 'No rain':
            rain_condition = 'No rain'
            rain_safe = True
        else:
            rain_condition = 'Unknown'
            rain_safe = False

        self.logger.debug('Rain Condition: {} '.format(rain_condition))

        return rain_condition, rain_safe

    def _get_wetness_safety(self, statuses):
        """Gets the wetness safety and weather conditions

        Args:
            statuses: The status of the weather data.

        Returns:
            The wetness condition and the rain safety. For example:

                'Dry', True
        """

        wetness_condition = statuses['boltwood_wet_flag']

        if wetness_condition == 'No data':
            wetness_safe = False
        elif wetness_condition == 'Wet':
            wetness_safe = False
        elif wetness_condition == 'Invalid':
            wetness_safe = False
        elif wetness_condition == 'Dry':
            wetness_safe = True
        else:
            wetness_condition = 'Unknown'
            wetness_safe = False

        self.logger.debug('Wetness Condition: {} '.format(wetness_condition))

        return wetness_condition, wetness_safe
