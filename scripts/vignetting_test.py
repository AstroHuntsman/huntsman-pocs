"""
Script to test vignetting at alt/az positions. While this code is designed to avoid damage from
looking at the Sun, it is strongly recommended to run only while the Sun is below the horizon.
"""
import sys
import time
import argparse
from datetime import datetime
import numpy as np

from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz

from panoptes.utils import utils
from pocs.scheduler.field import Field
from pocs.scheduler.observation import Observation
from huntsman.pocs.observatory import create_huntsman_observatory


class AltAzGenerator():
    """
    Class to generate alt-az positions uniformly over the sphere, that are a minimum distance
    away from the Sun and are at a minimum altitude. Used as an iterator.
    """

    def __init__(self, location, exposure_time, safe_sun_distance=40, min_altitude=30,
                 n_samples=100):
        self.location = location
        self.exposure_time = utils.get_quantity_value(exposure_time, u.second)
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
        times = np.linspace(0, time_period, sampling_interval)*u.second + time_now

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


class ExposureSequence():

    def __init__(self, observatory, filter_name, exposure_time, n_exposures=100,
                 field_name='DomeVigTest', **kwargs):
        self.observatory = observatory
        self.cameras = observatory.cameras
        self.mount = observatory.mount
        self.earth_location = observatory.earth_location
        self.field_name = field_name
        self.filter_name = filter_name
        self.exposure_time = utils.get_quantity_value(exposure_time, u.second) * u.second
        # Create the coordinate generator
        self.coordinates = AltAzGenerator(location=self.earth_location, n_samples=n_exposures,
                                          exposure_time=self.exposure_time, **kwargs)
        self.n_exposures = len(self.coordinates)  # May be different from n_exposures

    def run(self):
        """
        Prepare telescope and start exposure sequence.
        """
        # Unpark mount
        if self.mount.is_parked:
            print("Un-parking mount...")
            self.mount.unpark()
        # Wait for cameras to be ready
        print(f"Preparing {len(observatory.cameras)} cameras...")
        self.observatory.prepare_cameras()
        try:
            self._take_exposure_sequence()
        except Exception as err:
            print("Error encountered during exposure sequence.")
            raise(err)
        finally:
            # Finish up
            print("Parking mount...")
            self._park_mount()

    def _take_exposure_sequence(self):
        """
        Take the exposure sequence, moving the FW to the blank position between exposures.
        """
        print("Starting exposure sequence.")
        for i, (alt, az) in enumerate(self.coordinates):
            print(f"---------------------------------------------------------")
            print(f"Exposure {i+1} of {self.n_exposures}:")
            self._take_exposure(alt=alt, az=az, suffix=f'_{i}')

    def _take_exposure(self, alt, az, suffix=""):
        """
        Slew to coordinates, take exposures and return images.
        """
        # Unit conversions
        alt = utils.get_quantity_value(alt, u.degree)
        az = utils.get_quantity_value(az, u.degree)

        # Make observation
        field, observation = self._make_observation(alt, az)
        headers = {"ALT-MNT": f"{alt:.3f}", "AZ-MNT": f"{az:.3f}"}

        # Slew to field
        print(f"Slewing to alt={alt:.2f}, az={az:.2f}...")
        self._slew_to_field(field)

        # Take observations
        events = []
        print("Taking exposures...")
        for cam_name, cam in observatory.cameras.items():
            events.append(cam.take_observation(observation, headers=headers))

        # Block until finished exposing on all cameras
        print("Waiting for exposures...")
        while not all([e.is_set() for e in events]):
            time.sleep(1)

    def _slew_to_field(self, field):
        """Slew to the field, moving FWs to blank beforehand."""
        print(f"Moving filterwheels to blank position before slewing...")
        self._move_fws(filter_name="blank")
        self.mount.set_target_coordinates(field)
        self.mount.slew_to_target()

    def _park_mount(self):
        """Park mount after moving FWs to blank positions"""
        print(f"Moving filterwheels to blank position before parking...")
        self._move_fws(filter_name="blank")
        self.mount.park()

    def _make_observation(self, alt, az):
        """Make an observation for the alt/az position."""
        position = utils.altaz_to_radec(alt=alt, az=az, location=self.earth_location,
                                        obstime=utils.current_time())
        field = Field(self.field_name, position.to_string('hmsdms'))
        observation = Observation(field=field, filter_name=self.filter_name,
                                  exptime=self.exposure_time)
        return field, observation

    def _move_fws(self, filter_name):
        """Move all the FWs to the filter (blocking)."""
        fw_events = [c.filterwheel.move_to(filter_name) for c in self.cameras.values()]
        while not all([e.is_set() for e in fw_events]):
            time.sleep(1)


if __name__ == '__main__':

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--exposure_time', default=1, type=float)
    parser.add_argument('--filter_name', default="luminance", type=str)
    parser.add_argument('--n_exposures', default=100, type=int)
    parser.add_argument('--min_altitude', default=40, type=float)
    args = parser.parse_args()

    response = input("This script is intended to be run with the Sun below the horizon."
                     " Would you like to continue?")
    if response not in ["", "y", "Y", "yes", "Yes"]:
        sys.exit()

    # Create the observatory instance
    observatory = create_huntsman_observatory(with_autoguider=False)

    # Run exposure sequence
    ExposureSequence(observatory, exposure_time=args.exposure_time, filter_name=args.filter_name,
                     n_exposures=args.n_exposures, min_altitude=args.min_altitude).run()
