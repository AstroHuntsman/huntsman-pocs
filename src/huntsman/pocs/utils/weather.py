import requests
from contextlib import suppress

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
                     'Dew_Point',
                     'Ambient_Temperature',
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
SKYMAPPER_FLOAT_COLUMNS = ['Relative_Humidity',
                           'Dew_Point',
                           'Wind_Speed_Minimum',
                           'Wind_Speed_Average',
                           'Wind_Speed_Maximum',
                           'Sky_Minus_Ambient',
                           'Ambient_Temperature'
                           ]


def determine_alt_weather_safety(weather_data, weather_source_config):
    """
    Parse an alt weather source reading dictionary and determine if weather conditions should be
    considered safe.

    Args:
        source_config (dict): Config dictionary for alt weather source, defined in huntsman.yaml.
    """
    # if any of the specified bool flags are true, then weather is not safe
    bool_flags_check = not any([weather_data[k] for k in weather_source_config["bool_flags"]])

    # check parameters that should be above a certain threshold (ie temp degrees above dewpoint)
    gt_thresholds = weather_source_config['thresholds']['greater_than']
    # check parameters that should be below a certain threshold (ie humidity, wind speed etc)
    lt_thresholds = weather_source_config['thresholds']['less_than']
    threshold_data = weather_data['threshold_parameters']
    gt_thresholds_check = all([threshold_data[k] > v for k, v in gt_thresholds.items()])
    lt_thresholds_check = all([threshold_data[k] < v for k, v in lt_thresholds.items()])

    # store the safety decision in the dictionary and return it
    weather_data['safe'] = all([bool_flags_check, gt_thresholds_check, lt_thresholds_check])
    return weather_data


def get_aat_weather():
    """
    Fetch met weather data from AAO weather station. Returns a dictionary with entries
    specified by `AAT_COLUMNS`.

    Returns:
        dict: dictionary of aat weather readings.
    """
    response = requests.get(AAT_URL)
    # raise an exception if response was not successful
    response.raise_for_status()

    date, raw_data, _ = response.content.decode().split('\n')
    aat_dict = {name: value for name, value in zip(AAT_COLUMNS, raw_data.split('\t'))}
    aat_dict['date'] = date

    # Try and parse values to float
    for k, v in aat_dict.items():
        with suppress(ValueError):
            aat_dict[k] = float(v)

    # Explicitly parse is_raining to bool
    # At the time of writing this is the only boolean quantity coming from AAT
    aat_dict["is_raining"] = bool(aat_dict["is_raining"])

    # Create list of values to use in threshold checks in `determine_alt_weather_safety()`
    try:
        dewpoint_diff = round(aat_dict.get(
            'outside_temp', None) - aat_dict.get('outside_dewpoint', None), 1)
    except TypeError:
        # if one or both values are missing set dewpoint_diff to None
        dewpoint_diff = None

    aat_dict['threshold_parameters'] = {'humidity': aat_dict.get('outside_humidity', None),
                                        'wind_speed': aat_dict.get('wind_speed_avg', None),
                                        'dewpoint_diff': dewpoint_diff}
    return aat_dict


def get_skymapper_weather():
    """
    Fetch and parse the skymapper met_data html page. Returns a dictionary with entries
    specified by `SKYMAPPER_COLUMNS`.

    Returns:
        dict: dictionary of skymapper weather readings.
    """
    skymapper_response = requests.get(SKYMAPPER_URL)
    # raise a HTTPError if one occured
    skymapper_response.raise_for_status()
    sm_dict = parse_skymapper_data(skymapper_response)

    # Create list of values to use in threshold checks in `determine_alt_weather_safety()`
    try:
        dewpoint_diff = round(sm_dict.get('Ambient_Temperature',
                                          None) - sm_dict.get('Dew_Point', None), 1)
    except TypeError:
        # if one or both values are missing set dewpoint_diff to None
        dewpoint_diff = None

    sm_dict['threshold_parameters'] = {'humidity': sm_dict.get('Relative_Humidity', None),
                                       'wind_speed': sm_dict.get('Wind_Speed_Average', None),
                                       'dewpoint_diff': dewpoint_diff}
    return sm_dict


def parse_skymapper_data(skymapper_response):
    """
    Extract skymapper weather data from the html page.

    """
    # convert html bytes to list of strings and strip off html syntax stuff
    sm_data = [str(n, 'utf-8').strip('\n').strip('<b>').strip('<b> ').strip('</')
               for n in skymapper_response.content.split(b'<br>')]
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
    # finally convert boolean/float columns from strings to bool/float type
    sm_bools = set(SKYMAPPER_BOOLEAN_COLUMNS)
    sm_floats = set(SKYMAPPER_FLOAT_COLUMNS)
    for key, value in sm_dict.items():
        if key in sm_bools:
            # boolean columns will be strings of either 0, 1, True or False
            try:
                sm_dict[key] = bool(int(value))
            except ValueError:
                # ValueError will be raised when trying bool('False')
                sm_dict[key] = value == 'True'
        elif key in sm_floats:
            try:
                sm_dict[key] = float(value)
            except TypeError:
                # set value to None
                sm_dict[key] = None
    return sm_dict


def list_to_dict_entry(input):
    """ Take a list of strings and parse through looking for a string ending with a ':',
    if found, join the previous entries into one string and remove the ':' and leave
    remaining entries alone. If no ':' is found just return the list of strings unmodified.
    """
    output = input
    for index, item in enumerate(input):
        if item.endswith(':'):
            output = ['_'.join(input[0:index + 1]).strip(':')] + [input[index + 1:]]
            break
    return output
