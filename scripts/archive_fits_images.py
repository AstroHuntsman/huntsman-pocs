#!/usr/bin/env python
import click
import glob
import time
import shutil
import pathlib
from datetime import datetime, timedelta
from os import path


@click.command()
@click.option('--newfile-basedir',
              default="/var/huntsman/images/",
              help='Base directory to search for new files.')
@click.option('--archive-basedir',
              default="/var/huntsman/archive/",
              help='Base directory to archive new files.')
@click.option('--time-buffer',
              default=10,
              help='Number of seconds to wait before a new file is archived.')
@click.option('--test-mode',
              default=True,
              help='If true, move commands are printed to stdout, not run.')
def archive(newfile_basedir,
            archive_basedir,
            time_buffer,
            test_mode,
            image_types=["flats", "fields/*", "darks"],
            glob_string="/*/*/*.fits*"):

    # /var/huntsman/images/fields/Frb190608/2d194b0013090900/20200914T115628
    # /var/huntsman/images/darks/2014420013090900/20200917T052955

    delta_t = timedelta(seconds=time_buffer)

    try:
        while True:
            for image_type in image_types:
                now = datetime.now()
                # glob_query = newfile_basedir + "*"
                glob_path = path.join(newfile_basedir, image_type)
                print(glob_path + glob_string)
                fresh_files = glob.glob(glob_path + glob_string)
                for filename in fresh_files:
                    if test_mode:
                        print(filename, now, datetime.fromtimestamp(path.getmtime(filename)),
                              now - datetime.fromtimestamp(path.getmtime(filename)))
                    if now - datetime.fromtimestamp(path.getmtime(filename)) > delta_t:
                        move_file(filename, newfile_basedir, archive_basedir, test_mode)
            time.sleep(time_buffer)
    except KeyboardInterrupt:
        print('\n\nCtrl+C detected, halting fits image archiver\n\n')
    click.echo(archive_basedir)


def move_file(filename, src_basedir, dest_basedir, test_mode):
    dest_filename = filename.replace(src_basedir, dest_basedir)
    pathlib.Path(path.dirname(dest_filename)).mkdir(parents=True, exist_ok=True)

    if test_mode:
        print(f"TESTING - command that would be run is: mv {filename} {dest_filename}")
    else:
        shutil.move(filename, dest_filename)


if __name__ == '__main__':
    archive()
