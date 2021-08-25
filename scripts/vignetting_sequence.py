"""
Script to test vignetting at alt/az positions. While this code is designed to avoid damage from
looking at the Sun, it is strongly recommended to run only while the Sun is below the horizon.
"""
import os
import sys
import time
import argparse
from tempfile import TemporaryDirectory
from contextlib import suppress
import numpy as np

from datetime import datetime
from dateutil.parser import parse as parse_date_dateutil

from astropy.io import fits
from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz
from astropy.coordinates import EarthLocation
from astropy.coordinates import SkyCoord

from astroplan import Observer, FixedTarget
from astroplan.plots import plot_sky

from matplotlib import pylab as plt

from panoptes.utils import utils
from huntsman.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation
from huntsman.pocs.utils.huntsman import create_huntsman_observatory


def parse_date(object):
    """
    Parse a date as a `datetime.datetime`.
    Args:
        object (Object): The object to parse.
    Returns:
        A `datetime.datetime` object.
    """
    if type(object) is datetime:
        return object
    if type(object) is Time:
        return object.to_datetime()
    with suppress(AttributeError):
        object = object.strip("(UTC)")
    return parse_date_dateutil(object)


class AltAzGenerator():
    """
    Class to generate alt-az positions uniformly over the sphere, that are a minimum distance
    away from the Sun and are at a minimum altitude. Used as an iterator.
    """

    def __init__(self, location, exposure_time, safe_sun_distance=50, min_altitude=30,
                 n_samples=49):
        self.location = location
        self.set_exposure_time(exposure_time)
        self.safe_sun_distance = utils.get_quantity_value(safe_sun_distance, u.degree) * u.degree
        self.min_altitude = utils.get_quantity_value(min_altitude, u.degree) * u.degree
        # Create the coordinate grid
        self._coordinates = self._make_coordinate_grid(n_samples)
        self._visited = np.zeros(self._coordinates.shape[0], dtype="bool")
        print(f"Sampled {len(self)} alt/az coordinates.")

    def __len__(self):
        return self._coordinates.shape[0]

    def __iter__(self):
        return self

    def __next__(self):
        if self._visited.all():
            raise StopIteration
        return self._get_coordinate(exposure_time=self.exposure_time)

    def set_exposure_time(self, exposure_time):
        """Set the exposure time."""
        self.exposure_time = utils.get_quantity_value(exposure_time, u.second)

    def get_coordinate_list(self):
        coord_list = []
        for alt, az in self._coordinates:
            coord_list.append((alt, az))
        return(coord_list)

    def _get_coordinate(self, exposure_time, sleep_time=60, **kwargs):
        """
        Get the next alt/az coordinate that is safe.
        """
        while True:
            for i in range(len(self)):
                if self._visited[i]:
                    continue
                alt, az = self._coordinates[i]
                if self._is_safe(alt, az, **kwargs):
                    self._visited[i] = True
                    return alt, az
            print(f"No safe coordinates. Sleeping for {sleep_time}s.")
            time.sleep(sleep_time)

    def _is_safe(self, alt, az, sampling_interval=30, overhead_time=60):
        """
        Check a coordinate is far enough away from the sun for its whole exposure time + overhead.
        """
        # Get time array
        time_now = Time(datetime.now())
        time_period = self.exposure_time + overhead_time
        times = np.linspace(0, time_period, sampling_interval) * u.second + time_now

        # Calculate Solar position
        frame = AltAz(obstime=times, location=self.location)
        sunaltazs = get_sun(times).transform_to(frame)

        # Calculate angular separation
        coord = AltAz(alt=alt, az=az)

        return all([coord.separation(c) > self.safe_sun_distance for c in sunaltazs])

    def _make_coordinate_grid(self, n_samples):
        """
        Sample alt/az coordinates on a grid, favouring coordinates near zenith.
        """
        # Make the grid
        n_per_axis = int(np.floor(np.sqrt(n_samples)))
        min_altitude = utils.get_quantity_value(self.min_altitude, u.degree)
        az_array, alt_array = np.meshgrid(np.linspace(min_altitude, 90, n_per_axis),
                                          np.linspace(0, 360, n_per_axis))
        # Reshape and stack
        return np.vstack([az_array.reshape(-1), alt_array.reshape(-1)]).T * u.degree


class ExposureTimeCalculator():
    """
    Class to estimate the next exposure time required to keep the count rate steady.
    """

    def __init__(self, window_size=50, sizex=5496, sizey=3672, saturate=4094, target_scaling=0.16,
                 minumum_scaling=0.05):
        self._saturate = saturate
        window_size = int(window_size)
        r = window_size / 2
        self._xmin = int(sizex / 2 - r)
        self._ymin = int(sizey / 2 - r)
        self._xmax = self._xmin + window_size
        self._ymax = self._ymin + window_size
        self._target_counts = target_scaling * saturate
        self._saturate = saturate
        self._date_prev = None
        self._mean_counts_prev = None
        self._exptime_prev = None
        self._min_counts = minumum_scaling * saturate

    def add_exposure(self, filename):
        """
        Update the ETC with the previous exposure.
        """
        mean_counts = self._get_mean_counts(filename)
        # If the exposure is vignetted, a large change in counts may be observed
        # We want to ingore these cases for the next ETC
        if self._mean_counts_prev is not None:
            if mean_counts < self._min_counts:
                print("Counts are too low. Assuming vignetted and ignoring for ETC.")
                return
        self._mean_counts_prev = mean_counts
        self._date_prev, self._exptime_prev = self._extract_header(filename)

    def calculate_exptime(self, date, past_midnight):
        """
        Calculate the next exposure time given the datetime using previous exposure data.

        Args:
            date (Object): An object that can be interpreted as a date by `parse_date`.
            past_midnight (bool): True if currently past midnight. TODO: remove.
        """
        date = parse_date(date)
        elapsed_time = (date - self._date_prev).seconds
        exptime = self._exptime_prev * (self._target_counts / self._mean_counts_prev)
        sky_factor = 2.0 ** (elapsed_time / 180.0)
        if past_midnight:
            exptime = exptime / sky_factor
        else:
            exptime = exptime * sky_factor
        return exptime.to_value(u.second) * u.second

    def _get_mean_counts(self, filename, bias=35):
        data = fits.getdata(filename).astype("int32")
        mean_counts = data[self._ymin: self._ymax, self._xmin: self._xmax].mean() - bias
        if mean_counts >= self._saturate - bias:
            print("WARNING: Counts are saturated.")
        print(f"Mean counts: {mean_counts:.0f}")
        return mean_counts

    def _extract_header(self, filename):
        header = fits.getheader(filename)
        date = parse_date(header["DATE-OBS"])
        exposure_time = header["EXPTIME"] * u.second
        return date, exposure_time


class ExposureSequence():

    def __init__(self, observatory, filter_name, initial_exptime, n_exposures=100,
                 field_name='VigTest', min_exptime=0, max_exptime=10, safe_sun_distance=50,
                 **kwargs):
        self.observatory = observatory
        self.cameras = observatory.cameras
        self.mount = observatory.mount
        self.earth_location = observatory.earth_location
        self.field_name = field_name
        self.filter_name = filter_name
        self.inital_exptime = utils.get_quantity_value(initial_exptime, u.second) * u.second
        self.max_exptime = utils.get_quantity_value(max_exptime, u.second) * u.second
        self.min_exptime = utils.get_quantity_value(min_exptime, u.second) * u.second
        self.safe_sun_distance = safe_sun_distance
        # Create the coordinate generator
        self.coordinates = AltAzGenerator(location=self.earth_location, n_samples=n_exposures,
                                          exposure_time=initial_exptime,
                                          safe_sun_distance=safe_sun_distance, **kwargs)
        self.n_exposures = len(self.coordinates)  # May be different from n_exposures
        # Create the exposure time calculators
        self.etcs = {cam_name: ExposureTimeCalculator() for cam_name in self.cameras.keys()}
        self.image_dir = self.observatory.get_config("directories.images")

    def run(self):
        """
        Prepare telescope and start exposure sequence.
        """
        # Unpark mount
        if self.mount.is_parked:
            print("Un-parking mount...")
            self.mount.unpark()
        # Wait for cameras to be ready
        print(f"Preparing {len(self.observatory.cameras)} cameras...")
        self.observatory.prepare_cameras()
        try:
            self._take_exposure_sequence()
        except Exception as err:
            print("Error encountered during exposure sequence.")
            raise(err)
        finally:
            self._park_mount()

    def _take_exposure_sequence(self):
        """
        Take the exposure sequence, moving the FW to the blank position between exposures.
        """
        print("Starting exposure sequence.")
        for i, (alt, az) in enumerate(self.coordinates):
            calibrate_exptime = i == 0  # Only on the first exposure
            print("---------------------------------------------------------")
            print(f"Exposure {i+1} of {self.n_exposures}:")
            self._take_exposure(alt=alt, az=az, suffix=f'_{i}',
                                calibrate_exptime=calibrate_exptime)
            print("Finished.")

    def _take_exposure(self, alt, az, suffix="", calibrate_exptime=False):
        """
        Slew to coordinates, take exposures and return images.
        """
        # Unit conversions
        alt = utils.get_quantity_value(alt, u.degree)
        az = utils.get_quantity_value(az, u.degree)
        print(f"alt={alt:.2f}, az={az:.2f}.")

        # Perform exposure time calibration if required
        if calibrate_exptime:
            print("Calibrating exposure time...")
            self._calibrate_exptime(alt, az)
        exptime = self._get_next_exptime()
        print(f"Exposure time: {utils.get_quantity_value(exptime, u.second):.4f}.")

        # Make observation and get headers
        observation = self._make_observation(alt, az, exposure_time=exptime)
        headers = self.observatory.get_standard_headers(observation=observation)
        # These don't get written...
        headers.update({"ALT-MNT": f"{alt:.3f}", "AZ-MNT": f"{az:.3f}"})

        # Take observations
        self._take_blocking_observation(observation, headers=headers)

        # Update Alt-Az generator with most recent ET
        self.coordinates.set_exposure_time(exptime)

    def _take_blocking_observation(self, observation, headers={}, filename_dict=None):
        """
        """
        self._slew_to_field(observation.field)
        # We need to access the files to update the exposure times
        # This means we need to specify the filenames!
        if filename_dict is None:
            filename_dict = self._get_filenames(observation)

        events = []
        print("Taking exposures...")
        for cam_name, cam in self.observatory.cameras.items():
            filename = filename_dict[cam_name]
            events.append(cam.take_observation(observation, headers=headers, filename=filename))

        # Block until finished exposing on all cameras
        print("Waiting for exposures...")
        while not all([e.is_set() for e in events]):
            time.sleep(1)

        # Update ETCs
        for cam_name in self.cameras.keys():
            self.etcs[cam_name].add_exposure(filename_dict[cam_name])

    def _get_filenames(self, observation):
        """
        Return a dictionary of cam_name: filename for the given observation.
        """
        filename_dict = {}
        start_time = utils.current_time(flatten=True)
        for cam_name, camera in self.cameras.items():
            image_dir = os.path.join(observation.directory, camera.uid, start_time)
            filename_dict[cam_name] = os.path.join(image_dir,
                                                   f'{start_time}.{camera.file_extension}')
        return filename_dict

    def _slew_to_field(self, field):
        """Slew to the field, moving FWs to blank beforehand."""
        print("Moving filterwheels to blank position before slewing...")
        self._move_fws(filter_name="blank")
        self.mount.set_target_coordinates(field)
        print("Slewing to target...")
        self.mount.slew_to_target()

    def _park_mount(self):
        """Park mount after moving FWs to blank positions"""
        print("Moving filterwheels to blank position before parking...")
        self._move_fws(filter_name="blank")
        print("Parking mount...")
        self.mount.park()

    def _make_observation(self, alt, az, exposure_time):
        """Make an observation for the alt/az position."""
        position = utils.altaz_to_radec(alt=alt, az=az, location=self.earth_location,
                                        obstime=utils.current_time())
        field = Field(self.field_name, position.to_string('hmsdms'))
        observation = Observation(field=field, filter_name=self.filter_name, exptime=exposure_time)
        return observation

    def _move_fws(self, filter_name):
        """Move all the FWs to the filter (blocking)."""
        fw_events = [c.filterwheel.move_to(filter_name) for c in self.cameras.values()]
        while not all([e.is_set() for e in fw_events]):
            time.sleep(1)

    def _calibrate_exptime(self, alt, az):
        """Take initial exposures to determine appropriate exposure times.
        Args:
            alt (float): Altitude of observation.
            az (float): Azimuth of observation.
        """
        # Create observation with initial exposure time
        observation = self._make_observation(alt, az, exposure_time=self.inital_exptime)
        # Determine required exposure times
        with TemporaryDirectory(dir=self.image_dir) as tdir:
            # Store the exposures in the temp dir
            filename_dict = {}
            for cam_name in self.cameras.keys():
                filename_dict[cam_name] = os.path.join(tdir, f"{cam_name}.fits")
            # Set initial values for ETCs
            print(f"Taking ET calibration exposures of {self.inital_exptime}.")
            self._take_blocking_observation(observation, filename_dict=filename_dict)

    def _get_next_exptime(self):
        """
        Use the median estimate from the cameras to determine the next exptime.
        """
        exptimes = []
        for etc in self.etcs.values():
            exptime = etc.calculate_exptime(date=utils.current_time(),
                                            past_midnight=self.observatory.is_past_midnight)
            exptimes.append(utils.get_quantity_value(exptime, u.second))
        exptime = np.median(exptimes) * u.second
        if exptime >= self.max_exptime:
            print("WARNING: max exptime reached.")
            exptime = self.max_exptime
        elif exptime <= self.min_exptime:
            print("WARNING: min exptime reached.")
            exptime = self.min_exptime
        return exptime


def only_plot_locations(n_exposures,
                        initial_exptime,
                        safe_sun_distance,
                        min_altitude,
                        observatory_name='Siding Spring Observatory'):
    location = EarthLocation.of_site(observatory_name)
    observer = Observer.at_site(observatory_name)
    time_now = Time(datetime.now())

    sun_coord = get_sun(time_now)
    sun_fixed_target = FixedTarget(coord=SkyCoord(
        ra=sun_coord.ra.deg * u.degree, dec=sun_coord.dec.deg * u.degree))

    coordinates = AltAzGenerator(location=location,
                                 n_samples=n_exposures,
                                 exposure_time=initial_exptime,
                                 safe_sun_distance=safe_sun_distance,
                                 min_altitude=min_altitude)
    coordinate_list = coordinates.get_coordinate_list()

    fig = plt.figure(figsize=(12, 8.2))
    plt.title("Field locations. Sun's position is 'x'.")
    for coordinate in coordinate_list:
        alt, az = coordinate
        position = utils.altaz_to_radec(alt=alt, az=az, location=location,
                                        obstime=time_now)
        sc = SkyCoord(ra=position.ra.deg * u.degree,
                      dec=position.dec.deg * u.degree)
        ft = FixedTarget(coord=sc)

        plot_sky(ft, observer, time_now)

    plot_sky(sun_fixed_target, observer, time_now, style_kwargs={'marker': 'x'})
    fig.savefig('plot_vignetting_locations.png', dpi=200)


if __name__ == '__main__':

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--field_name', default='VigTest', type=str)
    parser.add_argument('--initial_exptime', default=0.0001, type=float)
    parser.add_argument('--max_exptime', default=30, type=float)
    parser.add_argument('--filter_name', default="luminance", type=str)
    parser.add_argument('--n_exposures', default=49, type=int)
    parser.add_argument('--min_altitude', default=50, type=float)
    parser.add_argument('--safe_sun_distance', default=50, type=float)
    parser.add_argument('--only_plot', default=False, type=bool)
    parser.add_argument('--daytime_mode', default=False, type=bool)
    args = parser.parse_args()

    if args.only_plot:
        only_plot_locations(n_exposures=args.n_exposures,
                            initial_exptime=args.initial_exptime,
                            safe_sun_distance=args.safe_sun_distance,
                            min_altitude=args.min_altitude,
                            )
        print("Only plotting locations then exiting.")
        sys.exit()

    if not args.daytime_mode:
        response = input("This script is intended to be run with the Sun below the horizon."
                         " Would you like to continue?")
        if response not in ["", "y", "Y", "yes", "Yes"]:
            sys.exit()
    else:
        response = input("You've indicated you would like to run this during the day."
                         "Would you like to continue?")
        if response not in ["y", "Y", "yes", "Yes"]:
            sys.exit()

    # Create the observatory instance
    observatory = create_huntsman_observatory(with_autoguider=False)

    # Run exposure sequence
    expseq = ExposureSequence(observatory, initial_exptime=args.initial_exptime,
                              filter_name=args.filter_name, n_exposures=args.n_exposures,
                              min_altitude=args.min_altitude, max_exptime=args.max_exptime,
                              field_name=args.field_name, safe_sun_distance=args.safe_sun_distance)
    expseq.run()
