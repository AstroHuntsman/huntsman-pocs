""" Code to facilitate delayed archiving of FITS files in the images directory """
import os
import time
import queue
import atexit
import shutil
from contextlib import suppress
from threading import Thread
from astropy import units as u

from panoptes.utils import get_quantity_value
from panoptes.utils.time import current_time
from panoptes.pocs.base import PanBase

VALID_EXTENSIONS = (".fits", ".fits.fz")


class Archiver(PanBase):
    """ Class to watch the images directory for new files and move them to the archive directory
    after enough time has passed.
    """
    _valid_extensions = VALID_EXTENSIONS

    def __init__(self, images_directory=None, archive_directory=None, delay_interval=None,
                 sleep_interval=None, status_interval=60, *args, **kwargs):
        """
        Args:
            images_directory (str): The images directory to archive. If None (default), uses
                the directories.images config entry.
            archive_directory (str): The archive directory. If None (default), uses
                the directories.archive config entry.
            delay_interval (u.Quantity): The minimum amount of time a file must spend in the
                archive queue before it is archived. If None (default), uses the
                archiver.delay_time config entry.
            sleep_interval (u.Quantity): The amout of time to sleep in between checking for new
                files to archive. Ideally this should be longer than delay_interval. If None
                (default), uses the archiver.sleep_interval confing entry.
            status_interval (float, optional): Sleep for this long between status reports. Default
                60s.
            *args, **kwargs: Parsed to PanBase initialiser.
        """
        super().__init__(*args, **kwargs)

        if images_directory is None:
            images_directory = self.get_config("directories.images")
        self.images_directory = str(images_directory)

        if archive_directory is None:
            archive_directory = self.get_config("directories.archive")
        self.archive_directory = str(archive_directory)
        self.logger.debug(f"Archive directory: {self.archive_directory}")

        if delay_interval is None:
            delay_interval = self.get_config("archiver.delay_interval")
        self.delay_interval = get_quantity_value(delay_interval, u.minute) * u.minute

        if sleep_interval is None:
            sleep_interval = self.get_config("archiver.sleep_interval")
        self.sleep_interval = get_quantity_value(sleep_interval, u.minute) * u.minute

        self._status_interval = get_quantity_value(status_interval, u.second)

        self._n_archived = 0
        self._stop = False
        self._archive_queue = queue.Queue()

        self._status_thread = Thread(target=self._async_monitor_status)
        self._watch_thread = Thread(target=self._async_watch_directory)
        self._archive_thread = Thread(target=self._async_archive_files)
        self._threads = [self._status_thread, self._watch_thread, self._archive_thread]

        atexit.register(self.stop)  # This gets called when python is quit

    @property
    def is_running(self):
        return self.status["is_running"]

    @property
    def status(self):
        """ Return a status dictionary.
        Returns:
            dict: The status dictionary.
        """
        status = {"is_running": all([t.is_alive() for t in self._threads]),
                  "status_thread": self._status_thread.is_alive(),
                  "watch_thread": self._watch_thread.is_alive(),
                  "archive_thread": self._status_thread.is_alive(),
                  "queued": self._archive_queue.qsize(),
                  "archived": self._n_archived}
        return status

    def start(self):
        """ Start archiving. """
        self.logger.info("Starting archiving.")
        self._stop = False
        for thread in self._threads:
            thread.start()

    def stop(self, blocking=True):
        """ Stop archiving.
        Args:
            blocking (bool, optional): If True (default), blocks until all threads have joined.
        """
        self.logger.info("Stopping archiving.")
        self._stop = True
        if blocking:
            for thread in self._threads:
                with suppress(RuntimeError):
                    thread.join()

    def _async_monitor_status(self):
        """ Report the status on a regular interval. """
        self.logger.debug("Starting status thread.")
        while True:
            if self._stop:
                self.logger.debug("Stopping status thread.")
                break
            # Get the current status
            status = self.status
            self.logger.debug(f"Archiver status: {status}")
            # Sleep before reporting status again
            time.sleep(self._status_interval)

    def _async_watch_directory(self):
        """ Watch the images directory and add all valid files to the archive queue. """
        self.logger.debug("Starting watch thread.")
        while True:
            if self._stop:
                self.logger.debug("Stopping watch thread.")
                break
            # Loop over filenames and add them to the queue
            # Duplicates are taken care of later on
            for filename in self._get_filenames_to_archive():
                self._archive_queue.put([current_time(), filename])
            # Sleep before checking again
            time.sleep(self.sleep_interval.to_value(u.second))

    def _async_archive_files(self, sleep=10):
        """ Archive files that have been in the queue longer than self.delay_interval.
        Args:
            sleep (float, optional): Sleep for this long while waiting for self.delay_interval to
                expire. Default: 10s.
        """
        while True:
            if self._stop and self._archive_queue.empty():
                self.logger.debug("Stopping archive thread.")
                break
            # Get the oldest file from the queue
            try:
                track_time, filename = self._archive_queue.get(block=True, timeout=sleep)
            except queue.Empty:
                continue
            # Archive file when it is old enough
            while current_time() - track_time < self.delay_interval:
                time.sleep(sleep)
            with suppress(FileNotFoundError):
                self._archive_file(filename)
                self._n_archived += 1
            # Tell the queue we are done with this file
            self._archive_queue.task_done()

    def _get_filenames_to_archive(self):
        """ Get valid filenames in the images directory to archive.
        Returns:
            list: The list of filenames to archive.
        """
        filenames = []
        # Get all the matching filenames in the images directory
        for path, _, files in os.walk(self.images_directory):
            for name in files:
                if any([name.endswith(ext) for ext in self._valid_extensions]):
                    filenames.append(os.path.join(path, name))
        return filenames

    def _get_archive_filename(self, filename):
        """ Get the archive filename from the original filename.
        Args:
            filename (str): The filename string.
        Returns:
            str: The archived file name.
        """
        relpath = os.path.relpath(filename, self.images_directory)
        return os.path.join(self.archive_directory, relpath)

    def _archive_file(self, filename):
        """ Archive the file.
        Args:
            filename (str): The filename string.
        """
        if not os.path.exists(filename):  # May have already been archived or deleted
            self.logger.warning(f"Tried to archive {filename} but it does not exist.")
            raise FileNotFoundError

        # Get the archived filename
        archive_filename = self._get_archive_filename(filename)
        # Make sure the archive directory exists
        os.makedirs(os.path.dirname(archive_filename), exist_ok=True)
        # Move the file to the archive directory
        self.logger.debug(f"Moving {filename} to {archive_filename}.")
        shutil.move(filename, archive_filename)
