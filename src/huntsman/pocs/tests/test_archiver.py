import os
import time
import pytest
from huntsman.pocs.archive import Archiver

N_IMAGES = 5


@pytest.fixture(scope="function")
def archiver(tmpdir):
    # Create temporary data directories
    images_dir = tmpdir.mkdir("images")
    archive_dir = tmpdir.mkdir("archive")
    # Fill images dir with fake images
    for i in range(N_IMAGES):
        fname = images_dir.join(f"fakeimage_{i}.fits")
        with open(fname, "w") as f:
            f.write("fake data")
        assert os.path.exists(fname)
    # Return the configured archiver for testing
    a = Archiver(images_directory=images_dir, archive_directory=archive_dir, status_interval=5)
    yield a
    a.stop()


def test_archiver_status(archiver):
    assert not archiver.status["is_running"]
    assert archiver.status["archived"] == 0
    archiver.start()
    assert archiver.status["is_running"]
    archiver.stop()
    assert not archiver.status["is_running"]
    assert not any([t.is_alive() for t in archiver._threads])


def test_archiver_archiving(archiver):
    assert len(os.listdir(archiver.archive_directory)) == 0
    assert len(os.listdir(archiver.images_directory)) == N_IMAGES
    assert archiver.status["archived"] == 0
    archiver.start()
    # Wait for the archiver to do the archiving
    time.sleep(archiver.sleep_interval.to_value("second") + 10)
    assert len(os.listdir(archiver.images_directory)) == 0
    assert len(os.listdir(archiver.archive_directory)) == N_IMAGES
    assert archiver.status["archived"] == N_IMAGES
