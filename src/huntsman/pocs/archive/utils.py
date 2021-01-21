import os
from contextlib import suppress


def remove_empty_directories(rootdir):
    """ Remove all empty directories inside rootdir, without deleting rootdir itself.
    Args:
        rootdir: The root directory to search for empty directories.
    """
    for path in os.listdir(rootdir):
        fullpath = os.path.join(rootdir, path)
        if os.path.isdir(fullpath):
            _remove_empty_directories(fullpath)


def _remove_empty_directories(path):
    """ Recursively delete all empty directories, including the top-level path.
    Args:
        path (str): The path to search for empty directories.
    """
    # If there is a file, the folder is not empty, so return False
    if not os.path.isdir(path):
        return False

    # Check if all subdirectories relative to this path are empty
    all_empty = True
    for filename in os.listdir(path):  # Have to loop over *all* subdirs
        all_empty &= _remove_empty_directories(os.path.join(path, filename))

    # If all of the subdirs were not empty, we need to delete this path
    # The empty subdirs will already have been deleted by the recursive call
    if all_empty:
        with suppress(OSError):
            os.rmdir(path)

    return all_empty
