#!/usr/bin/env python
"""Move fits files to a new base directory.
"""
import click
import glob
import time
import shutil
import pathlib
import sys
from datetime import datetime, timedelta
from os import path


@click.command()
@click.option('--test-mode/--run',
              default=True,
              help='If test-mode (default), commands are only printed to stdout.')
@click.option('--newfile-basedir',
              default="/var/huntsman/images/",
              help='Base directory to search for new files.')
@click.option('--archive-basedir',
              default="/var/huntsman/archive/",
              help='Base directory to archive new files.')
@click.option('--time-buffer',
              default=30,
              help='How old a file must be in second before it is archived.')
@click.option('--loop/--run-once',
              default=False,
              help="If --loop, script will continue to run until ctrl+c.")
@click.option('--glob-string',
              default="/*/*/*.fits*",
              help="Regular expression to find the files to archive")
@click.option('--ignore-string',
              default='TestTarget',
              help="Skip file if any part matches this string. Not fancy")
def archive(newfile_basedir,
            archive_basedir,
            time_buffer,
            test_mode,
            loop,
            glob_string,
            ignore_string,
            image_types=["flats", "fields/*", "darks"]):
    """Move files from one basedir + glob_string to another basedir. Useful
    for archiving files when you want to preserve full paths aside from
    the basedirs.

    Args:
        newfile_basedir (str): Base directory of where new files appear.
        archive_basedir (str): Base directory of where to archive files.
        time_buffer (float): How old a file must be in second before it is archived.
        test_mode (bool): If True, commands are only printed to stdout.
        loop (bool): If True, script will continue to run until ctrl+c.
        glob_string (str): File search string.
        ignore_string (str): Skip file if any part matches this string.
        image_types (list, optional): Names of first level directories after basedirs.
    """
    # /var/huntsman/images/fields/Frb190608/2d194b0013090900/20200914T115628
    # /var/huntsman/images/darks/2014420013090900/20200917T052955

    delta_t = timedelta(seconds=time_buffer)

    if time_buffer < 5:
        print('ERROR: time buffer must be > 5 to ensure the file has been written out')
        sys.exit(1)

    if not(test_mode):
        response = input("WARNING not in test mode, are you sure you want to really move the files? Type 'Yes' to confirm\n")
        print(response)
        if response.strip() != 'Yes':
            print(f"Response was not 'Yes' (case-sensitive) so exiting")
            sys.exit()
        else:
            print("\n\nOK, running for real.")
    else:
        print('\n\nRunning in test mode.\n\n')
    time.sleep(5)  # small delay so people can see what its about to do before it does it


    try:
        while True:
            for image_type in image_types:
                now = datetime.now()
                glob_path = path.join(newfile_basedir, image_type)
                print(f"Scanning: {glob_path}{glob_string}")
                fresh_files = glob.glob(glob_path + glob_string)
                for filename in fresh_files:
                    if ignore_string in filename:
                        continue
                    if now - datetime.fromtimestamp(path.getmtime(filename)) > delta_t:
                        move_file(filename, newfile_basedir, archive_basedir, test_mode)
            if not(loop):
                break

            time.sleep(time_buffer)
    except KeyboardInterrupt:
        print('\n\nCtrl+C detected, halting fits image archiver\n\n')


def move_file(filename, src_basedir, dest_basedir, test_mode):
    """Move a file to a new base directory, creating new folders
    if required in the new location.

    Args:
        filename (str): Full path to file that will be moved.
        src_basedir (str): String of the source base directory.
        dest_basedir (str): String of the destination base directory.
        test_mode (bool): If true, don't move, only print command to STDOUT.
    """
    dest_filename = filename.replace(src_basedir, dest_basedir)
    pathlib.Path(path.dirname(dest_filename)).mkdir(parents=True, exist_ok=True)

    if test_mode:
        print(f"TESTING - command that would be run is: mv {filename} {dest_filename}")
    else:
        print(f"moving {filename} {dest_filename}")
        shutil.move(filename, dest_filename)


if __name__ == '__main__':
    archive()
