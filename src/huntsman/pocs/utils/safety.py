from datetime import datetime

import numpy as np

from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz

from panoptes.utils.utils import get_quantity_value

import requests

AAT_URL = 'http://aat-ops.anu.edu.au/met/metdata.dat'
AAT_COLUMNS = ['time',
               'ambient_temp',
               'dome_temp',
               'mirror_temp',
               'outside_dewpoint',
               'outside_humidity',
               'pressure',
               'wind_speed_avg',
               'wind_gust_max',
               'wind_direction_avg',
               'unknown_3',
               'unknown_4',
               'unknown_5',
               'sky_ambient_diff_C',
               'sky_ambient_diff_error',
               'boltwood_wetness_meter_maybe',
               'unknown_7',
               'unknown_8',
               'rain_since_9am',
               'sqm_brightness',
               ]


def get_solar_altaz(time, location):
    """ Return the altaz of the Sun at a given time and location.
    Args:
        time (astropy.time.Time): The time of the observation.
        location (astropy.coordinates.EarthLocation): The location of the observation.
    Returns:
        astropy.coordinates.AltAz: The alt/az of the Sun.
    """
    frame = AltAz(obstime=time, location=location)

    sunaltaz = get_sun(time).transform_to(frame)

    return sunaltaz


def get_solar_separation(coord, time, location):
    """ Get the angular separation between a coordinate and the Sun at a given time & location.
    Args:
        coord (astropy.coordinates.SkyCoord): The coordinate.
        time (astropy.time.Time): The time of the observation.
        location (astropy.coordinates.EarthLocation): The location of the observation.
    Returns:
        astropy.Quantity: The angular separation.
    """
    frame = AltAz(obstime=time, location=location)

    # Calculate observation alt/az
    obsaltaz = coord.transform_to(frame)

    # Calculate Solar alt/az
    sunaltaz = get_solar_altaz(time, location)

    return obsaltaz.separation(sunaltaz)


def check_solar_separation_safety(observation, location, min_separation, time=None,
                                  overhead_time=120, time_check_interval=60):
    """ Check if the solar separation satisfies safety condition over observation time.
    Args:
        observation (Observation): The observation object.
        location (astropy.coordinates.EarthLocation): The location of the observation.
        min_separation (astropy.Quantity): The minimum safe separation.
        overhead_time (float, optional): Observation overhead time in seconds. Default 120s.
        time_check_interval (float, optional): Check safety at this interval in seconds.
            Default 60s.
    """
    coord = observation.field.coord
    min_separation = get_quantity_value(min_separation, u.deg) * u.deg

    exp_duration = get_quantity_value(observation.minimum_duration, u.second)
    overhead_time = get_quantity_value(overhead_time, u.second)
    time_check_interval = get_quantity_value(time_check_interval, u.second)

    if time is None:
        time = Time(datetime.now())

    # Evaluate safety at regular time intervals over observation
    obstime = exp_duration + overhead_time
    times = np.arange(0, obstime + time_check_interval, time_check_interval) * u.second + time

    # Calculate solar separation at each time
    separations = get_solar_separation(coord, times, location)

    return all([c > min_separation for c in separations])


def get_aat_weather(aat_url=AAT_URL, query_columns=AAT_COLUMNS):
    """Fetch met weather data from AAO weather station.

    Args:
        aat_url (string, optional): URL to query for weather reading. Defaults to AAT_URL.
        query_columns (list, optional): List of column names that map onto the values contained
        in a succesful query. Defaults to AAT_COLUMNS.
    """
    query = requests.get(aat_url)

    if query.ok:
        date, raw_data, _ = query.content.decode().split('\n')
        data = {name: value for name, value in zip(query_columns, raw_data.split('\t'))}
        data['date'] = date
    else:
        data = None

    return data
