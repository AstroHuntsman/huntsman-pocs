from pocs.mount import create_mount_from_config
from pocs.scheduler import create_scheduler_from_config 
from huntsman.camera import create_cameras_from_config
from huntsman.observatory import HuntsmanObservatory
from pocs.core import POCS
from huntsman.utils import load_config

# Import datetime to insert a timestamp in each image.
from datetime import datetime

import os

# Load Huntsman configuration
config = load_config()

# create cameras
cameras = create_cameras_from_config()
# Start exoplanet observation

# Create mount
mount = create_mount_from_config(config)
mount.initialize()

# create the scheduler
scheduler = create_scheduler_from_config(config)

# Create the observatory
observatory = HuntsmanObservatory(cameras=cameras, mount=mount,
                                  scheduler=scheduler,
                                  with_autoguider=True,
                                  take_flats=True)

# Create POCS
pocs = POCS(observatory, simulator=["power"])
pocs.initialize()

# Run POCS
pocs.run()

# Set the number of exposures to take.
number_calibrations = 20
# Set the exposure time in seconds.
exposure_times = [0.1, 120]
# Get the bias and darks for the night, and name the
# directory where the data will be saved.
night_date = datetime.utcnow().isoformat()[0:10]
data_directory = f"/var/huntsman/data_{night_date}"
images_dir = os.makedirs(data_directory, exist_ok=True)


# Output directory for bias and darks
bias_darks_dir = data_directory + "/bias_darks"
biasdarks_dir = os.makedirs(bias_darks_dir, exist_ok=True)

for i in range(number_calibrations):
    print(f"Starting exposures {i+1} of {number_calibrations}")
    exposure_events = []
    for camera in cameras.values():
        timestamp = datetime.utcnow().isoformat()
        name = f"bias_darks_dir/{camera.uid}/{timestamp}.fits"
        for exptime in exposure_times:
            exposure_events.append(camera.take_exposure(seconds=exptime,
                                                        filename=name,
                                                        dark=True))
            print(f"Exposure {name} started.")
        for e in exposure_events:
            e.wait()
