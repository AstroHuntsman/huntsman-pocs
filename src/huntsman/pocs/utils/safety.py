from contextlib import suppress
from datetime import datetime

import requests

import numpy as np

from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz

from panoptes.utils.utils import get_quantity_value


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
SKYMAPPER_URL = 'https://www.mso.anu.edu.au/~skymap/METS/met_data.html'
SKYMAPPER_COLUMNS = ['Date',
                     'Time',
                     'Raining',
                     'Cloudy',
                     'Humidity',
                     'Windy',
                     'Hailing',
                     'Excessive_Light',
                     'Internal_Rain_Sensor',
                     'External_Rain_Sensor',
                     'Relative_Humidity',
                     'Wind_Speed',
                     'Wind_Speed_Minimum',
                     'Wind_Speed_Average',
                     'Wind_Speed_Maximum',
                     'Sky_Minus_Ambient',
                     ]
SKYMAPPER_BOOLEAN_COLUMNS = ['Raining',
                             'Cloudy',
                             'Humidity',
                             'Windy',
                             'Hailing',
                             'Excessive_Light',
                             'Internal_Rain_Sensor',
                             'External_Rain_Sensor',
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

    date, raw_data, _ = response.content.decode().split('\n')
    data = {name: value for name, value in zip(response_columns, raw_data.split('\t'))}
    data['date'] = date

    # Try and parse values to float
    for k, v in data.items():
        with suppress(ValueError):
            data[k] = float(v)

    # Explicitly parse is_raining to bool
    # At the time of writing this is the only boolean quantity coming from AAT
    data["is_raining"] = bool(data["is_raining"])

    return data


def get_skymapper_weather():
    """
    Utility to fetch and parse the skymapper met_data html page. Returns a dictionary with entries specified
    by `SKYMAPPER_COLUMNS`

    Returns:
        dict: dictionary of skymapper weather readings
    """
    skymapper_response = requests.get(SKYMAPPER_URL)
    # raise a HTTPError if one occured
    skymapper_response.raise_for_status()
    sm_dict = parse_skymapper_data(skymapper_response)
    return sm_dict


def parse_skymapper_data(skymapper_response):
    """
    Extract skymapper weather data from the html page.

    """
    # convert html bytes to list of strings and strip off html syntax stuff
    sm_data = [ str(n, 'utf-8').strip('\n').strip('<b>').strip('<b> ').strip('</') for n in skymapper_response.content.split(b'<br>')]
    # delete first, second and last entries in list as it's just more html junk
    del sm_data[0:2]
    del sm_data[-1]
    # now remove empty strings from list
    sm_data[:] = [d for d in sm_data if d]
    # now split each string by white space
    sm_data = [d.split() for d in sm_data]
    # concanenate strings preceeding by a ':' to create the key entries for final data dict
    sm_data[:] = [list_to_dict_entry(d) for d in sm_data]
    # Convert the list of lists into a dict using only relevant columns
    sm_dict = dict()
    for item in sm_data:
        if item[0] in set(SKYMAPPER_COLUMNS):
            sm_dict[item[0]] = item[1][0]
    # finally convert boolean columns from strings to bool type
    for key, value in sm_dict.items():
        if key in set(SKYMAPPER_BOOLEAN_COLUMNS):
            # boolean columns will be strings of either 0, 1, True or False
            try:
                sm_dict[key] = bool(int(value))
            except ValueError:
                # ValueError will be raised when trying bool('False')
                sm_dict[key] = value=='True'
    return sm_dict


def list_to_dict_entry(input):
    """ Take a list of strings and parse through looking for a string ending with a ':',
    if found, join the previous entries into one string and remove the ':' and leave
    remaining entries alone. If no ':' is found just return the list of strings unmodified.
    """
    output=input
    for index, item in enumerate(input):
        if item.endswith(':'):
            output = ['_'.join(input[0:index+1]).strip(':')]+ [input[index+1:]]
            break
    return output
