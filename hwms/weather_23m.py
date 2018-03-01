#!/usr/bin/env python3

import logging
import re
import requests
import xmltodict

import astropy.units as u
from astropy.table import Table
from astropy.time import Time, TimeDelta

from datetime import datetime as dt

from . import load_config
from .weather_abstract import WeatherDataAbstract
from .weather_abstract import get_mongodb

class Met23Weather(WeatherDataAbstract):
    """ Gets the weather information from the 2.3 m telescope and checks if the
    weather conditions are safe.

    Met data from the 2.3 m is parsed into a dictionary from its original xml
    file, entries that were taken from the file are checked with customizable
    parameters to decide its condition and its safety.
    Information of the met data is then able to be stored in mongodb and sent to
    POCS.

    Attributes:
        self.met23_cfg: An dict that contains infromation about the met data.
        self.thresholds: An array of the thresholds for weather entries.
        self.logger: Used to create debugging messages.
        self.max_age: Maximum age of met data that is to be retrieved.
    """

    def __init__(self, use_mongo=True):
        # Read configuration
        self.config = load_config()
        self.met23_cfg = self.config['weather']['met23']
        self.thresholds = self.met23_cfg['thresholds']

        super().__init__(use_mongo=use_mongo)

        self.logger = logging.getLogger(name=self.met23_cfg.get('name'))
        self.logger.setLevel(logging.INFO)

        self.max_age = TimeDelta(self.met23_cfg.get('max_age', 360.), format='sec')

        self._safety_methods = {'rain_condition':self._get_rain_safety,
                                'wind_condition':self._get_wind_safety,
                                'gust_condition':self._get_gust_safety}

        self.table_data = None

    def capture(self, use_mongo=False, send_message=False, **kwargs):
        """ Update weather data. """
        self.logger.debug('Updating weather data')

        data = {}

        data['weather_data_name'] = self.met23_cfg.get('name')
        self.table_data = self.fetch_met23_data()

        col_names = self.met23_cfg.get('column_names')

        for name in col_names.keys():
            data[name] = self.table_data[name][0]

        self.weather_entries = data

        return super().capture(use_mongo=False, send_message=False, **kwargs)

    def fetch_met23_data(self):
        """ get the weather data from the 2.3 m and then parse the entries
        that are wanted into a table.

        Returns:
            Table of the 2.3m met data including the entries corresponding units.
        """
        try:
            cache_age = Time.now() - self.time
        except AttributeError:
            cache_age = 360.1 * u.second

        if cache_age > self.max_age:
            met23_link = self.met23_cfg.get('link')
            response = requests.get(met23_link)

            with open('met23.xml', 'wb') as file:
                file.write(response.content)

            with open('met23.xml') as fd:
                    doc = xmltodict.parse(fd.read())

            # turns the string of the rain condition into an integer number
            rain_stat = str(doc['metsys']['data']['rsens']['val'])

            if rain_stat == 'RAINING':
                rain_val = 1
            elif rain_stat == 'NOT_RAINING':
                rain_val = 0
            else:
                rain_val = -1

            # gets data from the xml file.
            data_rows = [(doc['metsys']['date'] + ' ' + doc['metsys']['utc'],
                          float(doc['metsys']['data']['ws']['val']),
                          float(doc['metsys']['data']['wgust']['val']),
                          float(doc['metsys']['data']['wd']['val']),
                          float(doc['metsys']['data']['wtt']['val']),
                          float(doc['metsys']['data']['tdb']['val']),
                          float(doc['metsys']['data']['dp']['val']),
                          float(doc['metsys']['data']['rh']['val']),
                          float(doc['metsys']['data']['qfe']['val']),
                          float(doc['metsys']['data']['qnh']['val']),
                          rain_val
                          )]

            col_names = self.met23_cfg.get('column_names')

            self.met23_table = Table(rows=data_rows, names=col_names.keys())

            # Set units for items
            for name, unit in col_names.items():
                self.met23_table[name].unit = unit

            self.time = Time.now()

        return(self.met23_table)

    def _get_rain_safety(self, statuses):
        """Gets the rain safety and weather conditions

        Args:
            statuses: The status of the weather data.

        Returns:
            The rain condition and the rain safety. For example:

                'No data', False
        """

        rain_condition = statuses['rain_sensor']

        if rain_condition == 'No data':
            rain_safe = False
        elif rain_condition == 'Rain':
            rain_safe = False
        elif rain_condition == 'Invalid':
            rain_safe = False
        elif rain_condition == 'No rain':
            rain_safe = True
        else:
            rain_condition = 'Unknown'
            rain_safe = False

        self.logger.debug('Rain Condition: {} '.format(rain_condition))

        return rain_condition, rain_safe
