""" Simple script to start archiving images. """
from huntsman.pocs.archive import Archiver

if __name__ == "__main__":

    archiver = Archiver()
    archiver.start()
