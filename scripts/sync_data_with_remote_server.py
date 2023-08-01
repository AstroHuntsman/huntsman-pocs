""" Simple script to start archiving images. """
import os
import time
import paramiko as pm
from huntsman.pocs.archive.archiver import Archiver

from panoptes.utils import error
from huntsman.pocs.utils.logger import get_logger
from astropy import units as u

VALID_EXTENSIONS = (".fits", ".fits.fz")


class RemoteArchiver(Archiver):
    """ Class to watch the archive directory on Huntsman control computer for new files and move
    them to the Data Central cloud after enough time has passed.
    """
    _valid_extensions = VALID_EXTENSIONS

    def __init__(self, images_directory=None, archive_directory=None, delay_interval=None,
                 sleep_interval=None, status_interval=60, logger=None, remote_host=None,
                 username=None, password=None, port=None, *args, **kwargs):
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
            logger (logger, optional): The logger instance. If not provided, use default Huntsman
                logger.
            remote_host (str): The name or IP address of the remote host to connect to.
            username (str): The username used to connect to the remote host.
            password (str): The password required to log in to the host.
            port (int): The port number used to connect to the remote host.
            *args, **kwargs: Parsed to PanBase initialiser.
        """
        if not logger:
            logger = get_logger()

        super().__init__(delay_interval=delay_interval, sleep_interval=sleep_interval,
                         images_directory=images_directory, archive_directory=archive_directory,
                         status_interval=status_interval, logger=logger, *args, **kwargs)
        if remote_host is None:
            remote_host = self.get_config("remote_host")
        self.remote_host = str(remote_host)
        self.logger.debug(f"Remote Host: {self.remote_host}")

        if username is None:
            username = self.get_config("username")
        self.username = str(username)
        self.logger.debug(f"Username: {self.username}")

        if password is None:
            password = self.get_config("password")
        self.password = str(password)

        if port is None:
            port = self.get_config("port")
        self.port = str(port)

    def _archive_file(self, filename):
        """Archive the file.
        Args:
            filename (str): The filename string.
        """
        if not os.path.exists(filename):  # May have already been archived or deleted
            self.logger.debug(f"Tried to archive {filename} but it does not exist.")
            raise FileNotFoundError

        # Get the archived filename
        upload_filename = self._get_archive_filename(filename)

        # # Make sure the upload directory exists
        # self._check_destination_directory()
        # os.makedirs(os.path.dirname(upload_filename), exist_ok=True)

        # Move the file to the DC directory
        self.logger.debug(f"Moving {filename} to {upload_filename}.")
        self.transfer_data(filename, upload_filename)

        # Finally, delete the original
        os.remove(filename)

    def _setup_sftp(self):
        self.ssh = pm.SSHClient()
        self.ssh.set_missing_host_key_policy(pm.AutoAddPolicy())
        self.ssh.connect(
            self.remote_host,
            username=self.username,
            password=self.password,
            port=self.port,
        )
        self.sftp = self.ssh.open_sftp()

    def transfer_data(self, filename, destination):
        self._setup_sftp()
        try:
            self.logger.info(
                "Checking whether the provided destination directory exists"
            )
            self.sftp.stat(os.path.dirname(destination))
            self.logger.info("The destination directory exisets in the cloud!")
        except FileNotFoundError:
            self.logger.info("The destination directory was not found!")
            self.logger.info(f"Creating {os.path.dirname(destination)} in the cloud.")
            folders = os.path.dirname(destination).split("/")
            for folder in folders:
                try:
                    self.sftp.chdir(folder)
                except FileNotFoundError:
                    # Create the folder if it does not exist
                    self.sftp.mkdir(folder)
                    self.sftp.chdir(folder)
            # self.sftp.mkdir(os.path.dirname(destination))
        self.logger.info(
            f"Copying {filename} into the destination directory: {destination}"
        )
        self.sftp.put(filename, destination)
        self.logger.info("Copying completed!")
        self.sftp.close()
        self.ssh.close()

if __name__ == "__main__":
    remote_host = "remote_host"
    username = "username"
    password = "password"
    port = int("port")
    images_directory = "images_directory"
    archive_directory = "path/to/huntsman/on/dc-cloud"

    delay_interval = 2 * u.second
    sleep_interval = 3 * u.second
    archiver = RemoteArchiver(
        delay_interval=delay_interval,
        sleep_interval=sleep_interval,
        images_directory=images_directory,
        archive_directory=archive_directory,
        remote_host=remote_host,
        username=username,
        password=password,
        port=port,
    )
    archiver.start()

    while True:
        if not archiver.is_running:
            raise error.PanError("Archiver is no longer running.")
        time.sleep(10)
