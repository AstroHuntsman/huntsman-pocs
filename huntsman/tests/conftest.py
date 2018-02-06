import os
import pytest

from pocs.utils.config import load_config
from pocs.utils.database import PanDB


def pytest_addoption(parser):
    parser.addoption(
        "--hardware-test",
        action="store_true",
        default=False,
        help="Test with hardware attached")
    parser.addoption(
        "--camera",
        action="store_true",
        default=False,
        help="If a real camera attached")
    parser.addoption("--mount", action="store_true", default=False,
                     help="If a real mount attached")
    parser.addoption(
        "--weather",
        action="store_true",
        default=False,
        help="If a real weather station attached")
    parser.addoption("--solve", action="store_true", default=False,
                     help="If tests that require solving should be run")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware-test"):
        # --hardware-test given in cli: do not skip harware tests
        return
    skip_hardware = pytest.mark.skip(reason="need --hardware-test option to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)


@pytest.fixture
def config():
    config = load_config(ignore_local=True, simulator=['all'])
    config['db']['name'] = 'huntsman_testing'
    return config


@pytest.fixture
def db():
    return PanDB()


@pytest.fixture
def data_dir():
    return '{}/pocs/tests/data'.format(os.getenv('POCS'))
