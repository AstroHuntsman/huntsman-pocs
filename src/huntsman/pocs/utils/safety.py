from datetime import datetime

import numpy as np

from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz

from panoptes.utils.utils import get_quantity_value


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
    exp_duration = observation.minimum_duration
    coord = observation.field.coord

    min_separation = get_quantity_value(min_separation, u.deg) * u.deg

    if time is None:
        time = Time(datetime.now())

    # Evaluate safety at regular time intervals over observation
    obstime = exp_duration + overhead_time
    times = np.arange(0, obstime + time_check_interval, time_check_interval) * u.second + time

    # Calculate solar separation at each time
    separations = get_solar_separation(coord, times, location)

    return all([coord.separation(c) > min_separation for c in separations])
