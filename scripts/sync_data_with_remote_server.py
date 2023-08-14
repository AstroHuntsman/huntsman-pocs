""" Simple script to start archiving images. """
import os
import sys
import time
import paramiko as pm
from huntsman.pocs.archive.archiver import Archiver

from panoptes.utils import error
from huntsman.pocs.utils.logger import get_logger
from huntsman.pocs.utils.config import get_config
from astropy import units as u

VALID_EXTENSIONS = (".fits", ".fits.fz")


class RemoteArchiver(Archiver):
    """ Class to watch the archive directory on Huntsman control computer for new files and transfer
    them to Data Central after enough time (delay_interval) has passed.
    """
    _valid_extensions = VALID_EXTENSIONS

    def __init__(
            self, images_directory, archive_directory, username, remote_host, port, pkey_path,
            delay_interval=None, sleep_interval=None, status_interval=60, logger=None, *args, **
            kwargs):
        """
        Args:
            images_directory (str): The images directory to archive. If None (default), uses
                the directories.images config entry.
            archive_directory (str): The archive directory. If None (default), uses
                the directories.archive config entry.
            username (str): The username for ssh access to remote host
            remote_host (str): The name or IP address of the remote host to connect to.
            port (int): The port number used to connect to the remote host.
            pkey_path (str): Filepath to ed25519 key for authenticating with the remote host.
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
            *args, **kwargs: Parsed to PanBase initialiser.
        """
        if not logger:
            logger = get_logger()

        super().__init__(images_directory=images_directory, archive_directory=archive_directory,
                         delay_interval=delay_interval, sleep_interval=sleep_interval,
                         status_interval=status_interval, logger=logger, *args, **kwargs)

        self.username = username
        self.remote_host = remote_host
        self.port = port
        self.private_key = pm.Ed25519Key(filename=pkey_path)

        self.logger.debug(
            f"Remote Host: {self.remote_host}, port: {self.port}, pkey_path: {pkey_path}")

    def _archive_file(self, filename):
        """Archive the file.
        Args:
            filename (str): The local filename string.
        """
        if not os.path.exists(filename):
            self.logger.debug(f"Tried to archive {filename} but it does not exist.")
            raise FileNotFoundError

        # Get the filename for the remote archive file
        remote_filename = self._get_archive_filename(filename)

        self.logger.debug(f"Moving {filename} to {remote_filename}.")
        success = self.transfer_data(filename, remote_filename)

        if success:
            self.logger.debug(f"Transfer successful, deleting {filename} on local machine.")
            os.remove(filename)
        else:
            self.logger.debug(
                "Transfer unsuccessful, archiver will reattempt upload at next iteration.")

    def transfer_data(self, local_filename, remote_filename):
        """Create an SFTP session and copy the local file to the remote host.

        Args:
            local_filename (str): local file to be copied
            remote_filename (str): the filename/path to copy the local file to on the remote host
        """
        success = False
        with pm.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(pm.AutoAddPolicy())
            ssh.connect(self.remote_host, port=self.port,
                        username=self.username, pkey=self.private_key)
            with ssh.open_sftp() as sftp:
                # FIRST verify directory structure exists on remote host and create it if it doesn't
                try:
                    self.logger.debug("Verify that the remote_filename directory exists")
                    sftp.stat(os.path.dirname(remote_filename))
                    self.logger.debug("Destination directory exists")
                except FileNotFoundError:
                    self.logger.info(
                        f"The {os.path.dirname(remote_filename)} directory was not found! \
                            Creating it now.")
                    # get the relative path of the remote_filename when compared with
                    # the archive directory on the remote machine
                    relpath = os.path.relpath(remote_filename, self.archive_directory)
                    folders = os.path.dirname(relpath).split("/")
                    folder_to_create = self.archive_directory
                    for folder in folders:
                        folder_to_create = os.path.join(folder_to_create, folder)
                        try:
                            sftp.chdir(folder_to_create)
                        except FileNotFoundError:
                            # Create the folder if it does not exist
                            sftp.mkdir(folder_to_create)

                # SECOND: copy file to desired location on remote host
                try:
                    self.logger.info(
                        f"Copying {local_filename} to destination directory: {remote_filename}"
                    )
                    # Note: when using confirm=True, sftp.put will check the file size after
                    # the transfer to confirm success
                    sftp.put(local_filename, remote_filename, confirm=True)
                except PermissionError as pe:
                    self.logger.warning(
                        f"Copying {local_filename} to {remote_filename} failed due to a \
                            permission error: {pe!r}")
                    return success
                except Exception as e:
                    self.logger.warning(
                        f"Copying {local_filename} to {remote_filename} failed due to an \
                            Exception: {e!r}")
                    return success

                # double check that filesize of the local and remote file match after transfer
                local_file_size = os.path.getsize(local_filename)
                remote_file_size = sftp.stat(remote_filename).st_size

                if local_file_size == remote_file_size:
                    success = True
                    self.logger.info("File transfer was successful: {success}")
                    return success
                else:
                    self.logger.info("File transfer was successful: {success}")
                    return success


if __name__ == "__main__":
    # required position args in order :
    # [images_directory, archive_directory, username, remote_host, port, pkey_path]
    args = list()
    args.append(get_config(key="remote_archiver.local_archive_directory", default=None))
    args.append(get_config(key="remote_archiver.remote_archive_directory", default=None))
    args.append(get_config(key="remote_archiver.username", default='huntsman'))
    args.append(get_config(key="remote_archiver.remote_host", default=None))
    args.append(get_config(key="remote_archiver.port", default=None))
    args.append(get_config(key="remote_archiver.private_key_path", default=None))

    arg_names = ["images_directory", "archive_directory",
                 "username", "remote_host", "port", "pkey_path"]
    for arg_value, arg_name in zip(args, arg_names):
        if arg_value is None:
            raise ValueError(f"{arg_name} must be specified, cannot be set to {arg_value}.")

    kwargs = dict()
    # The minimum amount of time a file must spend in the archive queue before it is uploaded
    kwargs['delay_interval'] = get_config(
        key="remote_archiver.delay_interval", default=300 * u.second)
    # how often the remote archiver checks for new local files to upload
    kwargs['sleep_interval'] = get_config(
        key="remote_archiver.sleep_interval", default=900 * u.second)

    archiver = RemoteArchiver(*args, **kwargs)
    archiver.start()

    try:
        while True:
            if not archiver.is_running:
                raise error.PanError("RemoteArchiver is no longer running.")
            time.sleep(60)
    except KeyboardInterrupt:
        archiver.logger.info(
            "KeyboardInterrupt received. Stopping the RemoteArchiver.")
        archiver.stop()

        archiver.logger.info("RemoteArchiver stopped.")
        sys.exit(0)
