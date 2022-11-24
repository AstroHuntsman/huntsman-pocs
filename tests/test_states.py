import os
import pytest

from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from huntsman.pocs.mount import create_mount_simulator
from panoptes.utils.config.client import set_config
from huntsman.pocs.dome import create_dome_simulator

from huntsman.pocs.core import HuntsmanPOCS
from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory as Observatory


@pytest.fixture(scope='function')
def cameras():
    return create_cameras_from_config()


@pytest.fixture(scope='function')
def mount():
    return create_mount_simulator()


@pytest.fixture
def observatory(mount, cameras, images_dir):
    """Return a valid Observatory instance with a specific config."""

    site_details = create_location_from_config()
    scheduler = create_scheduler_from_config(observer=site_details['observer'])

    obs = Observatory(scheduler=scheduler, cameras=cameras, mount=mount)

    return obs


@pytest.fixture(scope='function')
def dome():
    set_config('dome', {
        'brand': 'Simulacrum',
        'driver': 'simulator',
    })
    return create_dome_simulator()


@pytest.fixture(scope='function')
def pocs(observatory, dome):
    os.environ['POCSTIME'] = '2020-01-01 08:00:00'
    pocs = HuntsmanPOCS(observatory, run_once=True)
    pocs.observatory.set_dome(dome)
    pocs.observatory.close_dome()
    yield pocs
    pocs.power_down()


@pytest.fixture(scope="function")
def pocstime_prestartup():
    return '2021-04-29 06:15:00'


@pytest.fixture(scope="function")
def pocstime_flat():
    return '2021-04-29 08:15:00'


@pytest.fixture(scope="function")
def pocstime_focus():
    return '2021-04-29 08:30:00'


@pytest.fixture(scope="function")
def pocstime_observe():
    return '2021-04-29 11:10:00'


# ==============================================================================


def test_starting_darks(pocs, pocstime_flat):
    """ Test if the parking state transitions from sleeping into darks. """

    pocs.initialize()
    pocs.set_config('simulator', ['camera', 'mount', 'power'])
    assert not pocs.observatory.dome.is_open

    os.environ['POCSTIME'] = pocstime_flat
    assert pocs.is_dark(horizon="twilight_max")
    pocs.db.insert_current('weather', {'safe': False})
    assert not pocs.is_weather_safe()
    assert not pocs.observatory.dome.is_open
    print(type(pocs.observatory.dome))
    pocs.observatory.dome.unpark()

    pocs.startup()
    assert pocs.state == "starting"
    assert pocs.next_state == "taking_darks"
    assert not pocs.observatory.dome.is_open

    pocs.goto_next_state()
    assert pocs.state == "taking_darks"
    assert pocs.next_state == "starting"
    assert not pocs.observatory.dome.is_open


def test_starting_scheduling_flats(pocs, pocstime_flat):
    """ Test if scheduling successfully transitions into twilight_flat_fielding """

    pocs.initialize()
    pocs.set_config('simulator', ['camera', 'mount', 'weather', 'power'])
    assert not pocs.observatory.dome.is_open

    os.environ['POCSTIME'] = pocstime_flat
    assert pocs.is_dark(horizon="twilight_max")
    assert not pocs.is_dark(horizon="focus")
    assert pocs.observatory.is_twilight
    assert not pocs.observatory.dome.is_open

    pocs.startup()
    assert pocs.state == "starting"
    assert pocs.next_state == "scheduling"
    assert not pocs.observatory.dome.is_open

    pocs.goto_next_state()
    assert pocs.state == "scheduling"
    assert pocs.next_state == "twilight_flat_fielding"


def test_starting_scheduling_focus(pocs, pocstime_focus):
    """ Test if scheduling successfully transitions into focusing """

    pocs.initialize()
    pocs.set_config('simulator', ['camera', 'mount', 'weather', 'power'])

    os.environ['POCSTIME'] = pocstime_focus
    assert pocs.is_dark(horizon="focus")
    assert not pocs.is_dark(horizon="observe")
    assert not pocs.observatory.dome.is_open

    pocs.startup()
    assert pocs.state == "starting"
    assert pocs.next_state == "scheduling"
    assert not pocs.observatory.dome.is_open

    pocs.goto_next_state()
    assert pocs.state == "scheduling"
    assert pocs.next_state == "coarse_focusing"


def test_shutdown(pocs, pocstime_focus, pocstime_prestartup):
    """ Test that we can shutdown properly after going to parking """

    pocs.initialize()
    pocs.set_config('simulator', ['camera', 'mount', 'weather', 'power'])

    os.environ['POCSTIME'] = pocstime_focus
    assert pocs.is_dark(horizon="focus")
    assert not pocs.is_dark(horizon="observe")
    assert not pocs.observatory.dome.is_open

    # Enter the scheduling state
    pocs.startup()
    assert pocs.state == "starting"
    assert pocs.next_state == "scheduling"
    assert not pocs.observatory.dome.is_open
    pocs.goto_next_state()
    assert pocs.observatory.dome.is_open

    # Force the parking state
    pocs.next_state = "parking"

    # Loop through shutdown sequence and make sure everything is shutdown properly
    for state in ("parking", "parked", "housekeeping", "sleeping"):
        assert pocs.next_state == state
        pocs.goto_next_state()
        assert pocs.state == state
        assert pocs.observatory.mount.is_parked
        if pocs.state == "sleeping":
            # simulate pocs sleeping above startup horizon and ensure the dome gets closed
            os.environ['POCSTIME'] = pocstime_prestartup
            pocs.next_state == "sleeping"
            pocs.goto_next_state()
            assert pocs.state == "starting"
            pocs.next_state = "parking"
            pocs.goto_next_state()
            assert pocs.state == "parking"
            assert pocs.observatory.mount.is_parked
            assert pocs.observatory.dome.is_closed
