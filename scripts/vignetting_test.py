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
from pocs.sheduler.observation import Observation
from huntsman.pocs.observatory import create_huntsman_observatory


class AltAzGenerator():
    """
    Class to generate alt-az positions uniformly over the sphere, that are a minimum distance
    away from the Sun and are at a minimum altitude.
    """

    def __init__(self, location, safe_sun_distance=40, min_altitude=30, n_samples=100):
        self.location = location
        self.safe_sun_distance = utils.get_quantity_value(safe_sun_distance, u.degree) * u.degree
        self.min_altitude = utils.get_quantity_value(min_altitude, u.degree) * u.degree
        self._idx = 0
        self._coordinates = self._sample_coordinates(n_samples)
        self.n_samples = self._coordinates.shape[0]  # May be different to n_samples
        self._n_visited = 0
        print(f"Sampled {len(self._coordinates)} alt/az coordinates.")

    def generate(self, exposure_time):
        """Generate the next safe coordinate until all are visited."""
        if self._n_visited == self.n_samples:
            return
        yield self.get_coordinate(exposure_time=exposure_time)
        self._n_visited += 1

    def get_coordinate(self, exposure_time, **kwargs):
        """
        Get the next alt/az coordinate that is safe.
        """
        while True:
            if self._idx == len(self._coordinates):
                self._idx = 0
            alt, az = self._coordinates[self._idx]
            self._idx += 1
            if self._is_safe(alt, az, exposure_time=exposure_time, **kwargs):
                return alt, az

    def _is_safe(self, alt, az, exposure_time, sampling_interval=30, overhead_time=60):
        """
        Check a coordinate is far enough away from the sun for its whole exposure time + overhead.
        """
        # Get time array
        time_now = Time(datetime.now())
        time_period = exposure_time + overhead_time
        times = np.linspace(0, time_period, sampling_interval)*u.second + time_now

        # Calculate Solar position
        frame = AltAz(obstime=times, location=self.location)
        sunaltazs = get_sun(times).transform_to(frame)

        # Calculate angular separation
        coord = AltAz(alt=alt, az=az)

        return all([coord.separation(c) > self.safe_sun_distance for c in sunaltazs])

    def _sample_coordinates(self, n_samples):
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
        self.exposure_time = utils.get_quantity_value(exposure_time, u.second)
        # Create the coordinate generator
        self.coordinates = AltAzGenerator(location=self.earth_location, n_samples=n_exposures,
                                          **kwargs).generate(exposure_time=self.exposure_time)
        self.n_exposures = len(self.coordinates)

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
            self.mount.park()

    def _take_exposure_sequence(self):
        """
        Take the exposure sequence, moving the FW to the blank position between exposures.
        """
        print("Starting exposure sequence.")
        for i, (alt, az) in enumerate(self.coordinates):
            print(f"---------------------------------------------------------")
            print(f"Exposure {i+1} of {self.n_exposures}:")

            # Move the filterwheels into blank position before slewing
            print(f"Moving filterwheels to blank position before slewing...")
            self._move_fws(filter_name="blank")
            try:
                self._take_exposure(alt=alt, az=az, suffix=f'_{i}')
            finally:
                # Move the filterwheels into blank position before slewing
                print(f"Moving filterwheels to blank position after exposure...")
                self._move_fws(filter_name="blank")

    def _take_exposure(self, alt, az, suffix=""):
        """
        Slew to coordinates, take exposures and return images.
        """
        # Unit conversions
        alt = utils.get_quantity_value(alt, u.degree)
        az = utils.get_quantity_value(az, u.degree)

        # Make observation
        observation = self._make_observation(alt, az)
        headers = {"ALT-MNT": f"{alt:.3f}", "AZ-MNT": f"{az:.3f}"}

        # Slew to field
        print(f"Slewing to alt={alt:.2f}, az={az:.2f}...")
        self.mount.set_target_coordinates(observation.field)
        self.mount.slew_to_target()

        # Take observations
        events = []
        print("Taking exposures...")
        for cam_name, cam in observatory.cameras.items():
            events.append(cam.take_observation(observation, headers=headers))

        # Block until finished exposing on all cameras
        print("Waiting for exposures...")
        while not all([e.is_set() for e in events]):
            time.sleep(1)

    def _make_observation(self, alt, az):
        """Make an observation for the alt/az position."""
        position = utils.altaz_to_radec(alt=alt, az=az, location=self.earth_location,
                                        obstime=utils.current_time())
        field = Field(self.field_name, position.to_string('hmsdms'))
        observation = Observation(field=field, filter_name=self.filter_name,
                                  exposure_time=self.exposure_time)
        return observation

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
    parser.add_argument('--n_exposures', default=49, type=int)
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
