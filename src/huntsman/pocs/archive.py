""" Code to facilitate delayed archiving of FITS files in the images directory """
import os
import time
from threading import Thread, Queue
from astropy import units as u

from panoptes.utils import get_quantity_value
from panoptes.utils.time import current_time
from panoptes.pocs.base import PanBase


class Archiver(PanBase):
    """
    """

    def __init__(self, delay_interval=30*u.minute, sleep_interval=5*u.minute, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.images_directory = self.get_config("directories.images")
        self.archive_directory = self.get_config("directories.archive")

        if delay_interval is None:
            delay_interval = self.get_config("archive.delay_interval")
        self.delay_interval = get_quantity_value(delay_interval, u.minute) * u.minute

        if sleep_interval is None:
            sleep_interval = self.get_config("archive.sleep_interval")
        self.sleep_interval = get_quantity_value(sleep_interval, u.minute) * u.minute

        self._stop = False
        self._archive_queue = Queue()
        self._threads = [Thread(target=self._async_monitor_status),
                         Thread(target=self._async_watch_directory),
                         Thread(target=self._async_archive_files)]

    def start(self):
        """
        """
        self._stop = False
        for thread in self._threads:
            thread.start()

    def stop(self):
        """
        """
        self._stop = True
        for thread in self._threads:
            thread.join()

    def _async_watch_directory(self):
        """
        """
        self.logger.debug("Starting watch thread.")
        while True:
            if self._stop:
                self.logger.debug("Stopping watch thread.")
                break
            for filename in self._identify_filenames():
                self._archive_queue.put([current_time(), filename])
            self._sleep()

    def _async_archive_files(self, sleep=30):
        """
        """
        while True:
            if self._stop and self._archive_queue.empty():
                self.logger.debug("Stopping archive thread.")
                break
            # Get the oldest file from the queue and archive it when the time has expired
            track_time, filename = self._archive_queue.get()
            while current_time() - track_time < self.delay_interval:
                time.sleep(sleep)
            self._archive_file(filename)

    def _get_filenames_to_archive(self):
        """
        """
        filenames = []
        # Get all the matching filenames in the images directory
        for path, _, files in os.walk(self.images_dir):
            for name in files:
                if any([name.endswith(ext) for ext in self._valid_extensions]):
                    filenames.append(os.path.join(path, name))
        return filenames

    def _get_archive_filename(self, filename):
        """ Get the archive filename based on the original filename.
        This is obtained by replacing the images directory with the archive directory.
        """
        relpath = os.path.relpath(filename, self.images_directory)
        return os.path.join(self.archive_directory, relpath)

    def _archive_file(self, filename):
        """
        """
        if not os.path.exists(filename):  # May have already been archived or deleted
            self.logger.warning(f"Tried to archive {filename} but it does not exist.")

        # Move the file to the archive directory
        archive_filename = self._get_archive_file(filename)
        self.logger.debug(f"Archiving {filename} to {archive_filename}.")
        os.rename(filename, archive_filename)

    def _sleep(self):
        """
        """
        self.logger.debug(f"Sleeping for {self.sleep_interval}.")
        sleep_interval = self.sleep_interval.to_value(u.second)
        time.sleep(sleep_interval)
