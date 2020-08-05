"""Script to monitor dome status."""
import time
import numpy as np
import pandas as pd
from pocs.utils import current_time
from huntsman.dome.musca import HuntsmanDome
from huntsman.utils import load_config

KEYS = ["Battery", "Solar_A", "Status", "Shutter", "Door", "Switch"]

def monitor_loop(dome, interval=300, filename="/home/huntsman/domelog.csv"):
    while True:
        # Log dome status
        status = dome.status()
        dome.logger.debug(f"Dome status: {status}")

        # Also save in a format convenient for plotting
        series = pd.Series()
        for key in KEYS:
            series[key] = status.get(key, np.nan)
        series["time"] = str(current_time().value)
        with open(filename, 'a') as f:
            pd.DataFrame(series).T.to_csv(f, header=f.tell()==0)

        # Sleep
        time.sleep(interval)

if __name__ == "__main__":

    # Create dome instance
    config = load_config()
    dome = HuntsmanDome(config=config)

    # Start monitoring
    monitor_loop(dome, interval=30)
