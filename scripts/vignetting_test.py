"""
Script to test vignetting at alt/az positions.
"""
import os
import time
import numpy as np
import pandas as pd
from astropy import units as u
from astropy.io import fits

import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from pocs import utils
from pocs.scheduler.field import Field
from pocs.mount import create_mount_from_config
from pocs.scheduler import create_scheduler_from_config
from huntsman.camera import create_cameras_from_config
from huntsman.observatory import HuntsmanObservatory
from huntsman.utils import load_config


def load_simulated_config():
    """
    Load the simulated config.
    """
    config = load_config(ignore_local=True)
    config.update({
        'dome': {
            'brand': 'Simulacrum',
            'driver': 'simulator',
        },
        'mount': {
            'model': 'simulator',
            'driver': 'simulator',
            'serial': {
                'port': 'simulator'
            }
        },
    })
    return config


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


def take_exposures(observatory, alt, az, exptime, filter_name, suffix=""):
    """
    Slew to coordinates, take exposures and return images.
    """
    # Slew to field
    position = utils.altaz_to_radec(alt=alt, az=az, location=observatory.earth_location,
                                    obstime=utils.current_time())
    field = Field('DomeVigTest', position.to_string('hmsdms'))
    observatory.mount.set_target_coordinates(field)
    observatory.mount.slew_to_target()

    # Loop over cameras
    camera_events = {}
    for cam_name, cam in observatory.cameras.items():

        # Create filename
        path = observatory.config['directories']['images']
        filename = os.path.join(path, 'vigtest', f'{cam.uid}')
        filename += suffix + f".{cam.file_extension}"

        # Move filterwheel
        cam.filterwheel.move_to(filter_name, blocking=True)

        # Take exposure and get event
        exptime = exptime.to_value(u.second)
        camera_event = cam.take_exposure(filename=filename, exptime=exptime)
        camera_events[cam_name] = {'event': camera_event, 'filename': filename}

    # Block until finished exposing on all cameras
    while not all([info['event'].is_set() for info in camera_events.values()]):
        time.sleep(1)

    # Read the data
    images = {}
    for cam_name, cam in observatory.cameras.items():
        images[cam_name] = fits.getdata(camera_events[cam_name]['filename'])

        # Make check plot
        fig, ax = plt.subplots()
        vmin = np.quantile(images[cam_name], 0.05)
        vmax = np.quantile(images[cam_name], 0.95)
        ax.imshow(images[cam_name], vmin=vmin, vmax=vmax, cmap='binary')
        filename = os.path.join(path, 'vigtest', f'{cam.uid}')
        filename += suffix + ".png"
        plt.savefig(filename, bbox_inches='tight')

    return images


def take_dome_darks(*args, **kwargs):
    """
    Take dark frames to be used as a reference. Can be refreshed over the
    course of the calibration if sky conditions are changing.
    """
    # Require dome shutter to be closed
    # Should be automated in future
    input("The dome shutter must be closed to take dome darks. "
          "Press enter once the dome is closed to begin.")

    # Begin exposures and wait for them to finish
    return take_exposures(*args, **kwargs)


def measure_vignetted_fraction(image, dome_dark, sigma=5):
    """
    Calculate vignetted fraction assuming that the sky is significantly
    brighter than inside of the dome.
    """
    rms = dome_dark.std()
    vigfrac = ((image - dome_dark) <= sigma * rms).mean()
    return vigfrac


def measure_vignetted_fractions(images, dome_darks):
    """
    Measure the vignettied fraction for each camera.
    """
    # Loop over exposures and measure vignetted fraction
    fractions = np.zeros(len(images))
    for i, cam_name in enumerate(images.keys()):
        fractions[i] = measure_vignetted_fraction(
                                images[cam_name], dome_darks[cam_name])
    return fractions


def run_test(observatory, alt_min=30, exptime=5*u.second, alt_dark=60,
             az_dark=90, filename=None, n_samples=50, filter_name="luminance"):
    """

    """
    # Get the alt/az coordinates
    print("Obtaining alt/az samples...")
    alt_array, az_array = sample_coordinates(n_samples, alt_min)
    n_samples = alt_array.size
    print(f"Number of samples: {alt_array.size}")

    # Wait for cameras to be ready
    print("Preparing cameras...")
    observatory.prepare_cameras()

    # Take dome darks
    print("Taking dome darks...")
    dome_darks = take_dome_darks(observatory, alt_dark, az_dark, exptime, filter_name,
                                 suffix='_dark')

    # Make sure dome shutter is open
    input("The dome shutter must be open. "
          "Press enter once the dome is open to continue.")

    # Measure vignetting
    print("Measuring vignetting...")
    vig_fractions = np.zeros((n_samples, len(cameras)))
    for i, (alt, az) in enumerate(zip(alt_array, az_array)):

        print(f"Exposure {i+1} of {n_samples}...")

        # Take the exposures
        images = take_exposures(observatory, alt, az, exptime, filter_name, suffix=f'_{i}')

        # Calculate vignetted fractions
        vig_fractions[i, :] = measure_vignetted_fractions(images, dome_darks)
    print("Done!")

    # Write the output file
    df = pd.DataFrame()
    df['alt'] = alt_array
    df['az'] = az_array
    for i, cam in enumerate(cameras.values()):
        df[f"{cam.uid}"] = vig_fractions[:, i]
    if filename is None:
        filename = os.path.join(os.environ["HOME"], "vigtest.csv")
    df.to_csv(filename)

    # Finish up
    mount.park()
    return df


if __name__ == '__main__':

    """
    alt_array, az_array = sample_coordinates(50, 10, makeplots=True)
    print(alt_array.size)
    plt.show(block=False)
    """

    simulate = False

    # Load the config
    if simulate:
        config = load_simulated_config()
    else:
        config = load_config()

    # Create the observatory instance
    cameras = create_cameras_from_config(config)
    mount = create_mount_from_config(config)
    mount.initialize()
    mount.unpark()
    scheduler = create_scheduler_from_config(config)
    observatory = HuntsmanObservatory(cameras=cameras, mount=mount, scheduler=scheduler)

    # Run
    df = run_test(observatory, exptime=1*u.second, n_samples=20)
