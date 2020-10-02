"""
Script to test vignetting at alt/az positions.
"""
import os
import time
import argparse
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

from astropy.io import fits
from astropy import units as u

from panoptes.utils import utils
from pocs.scheduler import Field
from huntsman.pocs.observatory import create_observatory_from_config


def sample_coordinates(n_samples, alt_min, makeplots=False):
    """
    Sample alt/az coordinates using Fibonachi sphere method.
    https://stackoverflow.com/questions/9600801/evenly-distributing-n-points-on-a-sphere
    """
    alt_array = []
    az_array = []
    points = []
    phi = np.pi * (3. - np.sqrt(5.))  # golden angle in radians

    for i in range(n_samples):
        y = 1 - (i / float(n_samples - 1)) * 2  # y goes from 1 to -1
        radius = np.sqrt(1 - y * y)  # radius at y
        theta = phi * i  # golden angle increment
        x = np.cos(theta) * radius
        z = np.sin(theta) * radius

        # Convert to alt / az
        alt = -np.arccos(z) * 180 / np.pi + 90
        az = np.arccos(x) * 180 / np.pi - 90
        if alt >= alt_min:
            alt_array.append(alt)
            az_array.append(az)
            points.append([x, y, z])

    alt_array = np.array(alt_array)
    az_array = np.array(az_array)

    if makeplots:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        ax.plot([p[0] for p in points], [p[1] for p in points],
                zs=[p[2] for p in points], color='k', marker='o',
                linestyle=None, linewidth=0, markersize=1)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
        ax.set_zlim(-1, 1)

    return alt_array, az_array


def take_exposures(observatory, alt, az, exposure_time, output_directory, suffix=""):
    """
    Slew to coordinates, take exposures and return images.
    """
    # Define field
    position = utils.altaz_to_radec(alt=alt, az=az, location=observatory.earth_location,
                                    obstime=utils.current_time())
    field = Field('DomeVigTest', position.to_string('hmsdms'))
    observatory.mount.set_target_coordinates(field)

    # Slew to field
    print(f"Slewing to alt={alt}, az={az}...")
    observatory.mount.slew_to_target()

    # Loop over cameras
    events = []
    filenames = []
    exposure_time = exposure_time.to_value(u.second)
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


def run_exposure_sequence(observatory, alt_min=30, exposure_time=5*u.second,
                          n_samples=50, filter_name="luminance"):
    """

    """
    # Wait for cameras to be ready
    print(f"Preparing {len(observatory.cameras)} cameras...")
    observatory.prepare_cameras()

    # Move the filterwheels into position
    print(f"Moving filterwheels to {filter_name}...")
    for cam in observatory.cameras.values():
        cam.filterwheel.move_to(filter_name, blocking=True)

    # Get the alt/az coordinates
    print("Obtaining alt/az coordinates...")
    alt_array, az_array = sample_coordinates(n_samples, alt_min)
    n_samples = alt_array.size

    # Specify output directory
    timestr = datetime.now().strftime("%Y-%m-%d:%H-%M-%S")
    path = observatory.config['directories']['images']
    output_directory = os.path.join(path, timestr)
    print(f"The output directory is {output_directory}.")
    if os.path.exists(output_directory):
        raise FileExistsError("Output directory already exsts.")

    # Start exposures
    print("Starting exposure sequence...")
    for i, (alt, az) in enumerate(zip(alt_array, az_array)):
        print(f"Exposure {i+1} of {n_samples}...")
        # Take the exposures
        take_exposures(observatory, alt=alt, az=az, exposure_time=exposure_time,
                       output_directory=output_directory, suffix=f'_{i}')

    # Finish up
    print("Parking mount...")
    observatory.mount.park()


if __name__ == '__main__':

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--exposure_time', default=1, type=float)
    parser.add_argument('--filter_name', default="luminance", type=str)
    parser.add_argument('--n_samples', default=50, type=int)
    args = parser.parse_args()

    # Create the observatory instance
    observatory = create_observatory_from_config()

    # Run exposure sequence
    run_exposure_sequence(observatory, n_samples=args.n_samples, filter_name=args.filter_name,
                          exposure_time=args.exposure_time)
