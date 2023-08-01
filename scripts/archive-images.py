""" Simple script to start archiving images. """
import time
from panoptes.utils import error
from huntsman.pocs.archive.archiver import Archiver

if __name__ == "__main__":

    archiver = Archiver()
    archiver.start()

    # Monitor the archiver
    # If it breaks we want to terminate the script so docker can restart the service
    while True:
        if not archiver.is_running:
            raise error.PanError("Archiver is no longer running.")
        time.sleep(10)
