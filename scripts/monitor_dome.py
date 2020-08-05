"""Script to monitor dome status."""
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pocs.utils import current_time
from huntsman.dome.musca import HuntsmanDome
from huntsman.utils import load_config

KEYS = ["Battery", "Solar_A", "Status", "Shutter", "Door", "Switch"]

def monitor_loop(dome, interval=60, filename_csv="/home/huntsman/domelog.csv",
                 filename_plot="/home/huntsman/domelog.png"):
    while True:
        # Log dome status
        status = dome.status()
        dome.logger.debug(f"Dome status: {status}")

        # Also save in a format convenient for plotting
        series = pd.Series()
        for key in KEYS:
            series[key] = status.get(key, np.nan)
        series["time"] = str(current_time().value)
        with open(filename_csv, 'a') as f:
            pd.DataFrame(series).T.to_csv(f, header=f.tell()==0, index=False)

        # Update plot
        df = pd.read_csv(filename_csv)
        n_plot = int(8640/interval)
        fig = plt.figure(figsize=(10, 4))
        ax0 = plt.subplot(2, 1, 1)
        y = df["Battery"].values[-n_plot:]
        x = np.arange(y.size)
        ax0.plot(x, y)
        # ax0.set_xticks(x[::30], y[::30])
        ax0.set_title("Battery")
        ax1 = plt.subplot(2, 1, 2)
        y = df["Solar_A"].values
        ax1.plot(x, y)
        # ax1.set_xticks(x[::30], [::30])
        plt.tight_layout()
        plt.savefig(filename_plot, dpi=150, bbox_inches='tight')

        # Sleep
        time.sleep(interval)

if __name__ == "__main__":

    # Create dome instance
    config = load_config()
    dome = HuntsmanDome(config=config)

    # Start monitoring
    monitor_loop(dome, interval=30)
