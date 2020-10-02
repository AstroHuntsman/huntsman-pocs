"""
Script to test vignetting at alt/az positions. While this code is designed to avoid damage from
looking at the Sun, it is strongly recommended to run only while the Sun is below the horizon.
"""
import os
import sys
import time
import argparse
from datetime import datetime
import numpy as np

from astropy.io import fits
from astropy import units as u
from astropy.time import Time
from astropy.coordinates import get_sun, AltAz, EarthLocation

from panoptes.utils import utils
from pocs.scheduler.field import Field
from huntsman.pocs.observatory import create_huntsman_observatory


class AltAzGenerator():
    """
    Class to generate alt-az positions uniformly over the sphere, that are a minimum distance
    away from the Sun and are at a minimum altitude.
    """

    def __init__(self, location, safe_sun_distance=40, alt_min=30, n_samples=10000):
        self.location = EarthLocation(lat=location["latitude"], lon=location["longitude"],
                                      height=location["elevation"])
        self.safe_sun_distance = utils.get_quantity_value(safe_sun_distance, u.degree) * u.degree
        self.alt_min = utils.get_quantity_value(alt_min, u.degree) * u.degree
        self._n_samples = n_samples
        self._coordinates = self._sample_coordinates()
        print(f"Sampled {len(self._coordinates)} alt/az coordinates.")

    def get_coordinate(self, exposure_time, **kwargs):
        """
        Get a random alt/az coordinate that is safe.
        """
        while True:
            for idx in range(len(self._coordinates)):
                alt, az = self._coordinates[idx]
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

    def _sample_coordinates(self):
        """
        Sample alt/az coordinates using Fibonachi sphere method.
        https://stackoverflow.com/questions/9600801/evenly-distributing-n-points-on-a-sphere
        """
        phi = np.pi * (3. - np.sqrt(5.))  # golden angle in radians
        coordinates = []
        for i in range(self._n_samples):
            y = 1 - (i / float(self._n_samples - 1)) * 2  # y goes from 1 to -1
            radius = np.sqrt(1 - y * y)                   # radius at y
            theta = phi * i                               # golden angle increment
            x = np.cos(theta) * radius
            z = np.sin(theta) * radius
            # Convert to alt / az
            alt = (-np.arccos(z) * 180 / np.pi + 90) * u.degree
            az = (np.arccos(x) * 180 / np.pi - 90) * u.degree
            if alt >= self.alt_min:
                coordinates.append([alt, az])
        return coordinates


def _move_fws(observatory, filter_name):
    fw_events = [c.filterwheel.move_to(filter_name) for c in observatory.cameras.values()]
    while not all([e.is_set() for e in fw_events]):
        time.sleep(1)


def take_exposures(observatory, alt, az, exposure_time, filter_name, output_directory, suffix=""):
    """
    Slew to coordinates, take exposures and return images.
    """
    # Unit conversions
    alt = utils.get_quantity_value(alt, u.degree)
    az = utils.get_quantity_value(alt, u.degree)
    exposure_time = utils.get_quantity_value(exposure_time, u.second)

    # Define field
    position = utils.altaz_to_radec(alt=alt, az=az, location=observatory.earth_location,
                                    obstime=utils.current_time())
    field = Field('DomeVigTest', position.to_string('hmsdms'))
    observatory.mount.set_target_coordinates(field)

    # Move the filterwheels into blank position for slew
    print(f"Moving filterwheels to blank position before slewing...")
    _move_fws(observatory, filter_name="blank")

    # Slew to field
    print(f"Slewing to alt={alt:.2f}, az={az:.2f}...")
    observatory.mount.slew_to_target()

    # Move the filterwheels into position
    print(f"Moving filterwheels to {filter_name}...")
    _move_fws(observatory, filter_name=filter_name)

    # Loop over cameras
    events = []
    filenames = []
    print("Taking exposures...")
    for cam_name, cam in observatory.cameras.items():

        # Create filename
        filename = os.path.join(output_directory, f'{cam.uid}')
        filename += suffix + f".{cam.file_extension}"

        # Take exposure and get event
        events.append(cam.take_exposure(filename=filename, seconds=exposure_time))
        filenames.append(filename)

    # Block until finished exposing on all cameras
    print("Waiting for exposures...")
    while not all([e.is_set() for e in events]):
        time.sleep(1)

    # Now we need to edit the fits headers to add alt-az info
    for filename in filenames:
        with fits.open(filename, 'update') as f:
            for hdu in f:
                hdu.header['ALT-MNT'] = f"{alt:.3f}"
                hdu.header['AZ-MNT'] = f"{az:.3f}"


def run_exposure_sequence(observatory, altaz_generator, alt_min=30, exposure_time=5,
                          n_exposures=50, filter_name="luminance"):
    """

    """
    if observatory.mount.is_parked:
        print("Un-parking mount...")
        observatory.mount.unpark()

    # Wait for cameras to be ready
    print(f"Preparing {len(observatory.cameras)} cameras...")
    observatory.prepare_cameras()

    # Specify output directory
    timestr = datetime.now().strftime("%Y-%m-%d:%H-%M-%S")
    output_directory = os.path.join(observatory.config['directories']['images'], "vigtest",
                                    timestr)
    print(f"The output directory is: {output_directory}.")
    if os.path.exists(output_directory):
        raise FileExistsError("Output directory already exists.")

    try:
        # Start exposures
        print("Starting exposure sequence...")
        for i in range(n_exposures):
            # Sample a safe coordinate
            alt, az = altaz_generator.get_coordinate(exposure_time=exposure_time)
            print(f"---------------------------------------------------------")
            print(f"Exposure {i+1} of {n_exposures}:")
            # Take the exposures
            take_exposures(observatory, alt=alt, az=az, exposure_time=exposure_time,
                           output_directory=output_directory, suffix=f'_{i}',
                           filter_name=filter_name)
    except Exception as err:
        print("Premature termination due to error.")
        raise(err)
    finally:
        # Move the filterwheels back into blank position
        print(f"Moving filterwheels to blank position...")
        _move_fws(observatory, filter_name="blank")

        # Finish up
        print("Parking mount...")
        observatory.mount.park()


if __name__ == '__main__':

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--exposure_time', default=1, type=float)
    parser.add_argument('--filter_name', default="luminance", type=str)
    parser.add_argument('--n_exposures', default=50, type=int)
    parser.add_argument('--min_altitude', default=40, type=float)
    args = parser.parse_args()

    response = input("This script is intended to be run with the Sun below the horizon."
                     " Would you like to continue?")
    if response not in ["", "y", "Y", "yes", "Yes"]:
        sys.exit()

    # Create the observatory instance
    observatory = create_huntsman_observatory(with_autoguider=False)

    # Create the coordinate generator
    altaz_generator = AltAzGenerator(location=observatory.location, alt_min=args.min_altitude)

    # Run exposure sequence
    run_exposure_sequence(observatory, n_exposures=args.n_exposures, filter_name=args.filter_name,
                          exposure_time=args.exposure_time, altaz_generator=altaz_generator)
