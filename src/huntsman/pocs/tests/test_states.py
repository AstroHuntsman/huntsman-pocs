import os
import pytest

from panoptes.utils import current_time

from panoptes.pocs.core import POCS
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.mount import create_mount_simulator
from panoptes.utils.config.client import set_config
from panoptes.pocs.dome import create_dome_simulator

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
    pocs = POCS(observatory, run_once=True)
    pocs.observatory.set_dome(dome)
    yield pocs
    pocs.power_down()


# ==============================================================================


def test_entering_darks_state(pocs):
    '''
    Test if parked state transitions to taking_darks given the required
    conditions, namely that it is dark and cannot observe (i.e. bad weather).
    '''
    pocs.initialize()
    assert pocs.is_initialized is True
    pocs.get_ready()

    pocs.set_config('simulator', ['camera', 'mount', 'night'])

    # Insert a dummy night
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'
    # Make sure it is dark.
    assert (pocs.is_dark(horizon='observe'))

    # Insert a dummy weather record
    pocs.db.insert_current('weather', {'safe': False})
    # Make sure the weather is *not* safe to observe.
    assert not pocs.is_weather_safe()

    pocs.next_state = 'parking'
    for state in ['parking', 'parked', 'taking_darks']:
        assert pocs.next_state == state
        pocs.goto_next_state()
        assert pocs.state == state


def test_parking_ready(pocs):
    '''
    Test if the parking state transitions back into ready.
    '''
    pocs.initialize()
    pocs.get_ready()
    pocs.set_config('simulator', ['camera', 'mount'])
    os.environ['POCSTIME'] = '2020-04-29 23:00:00'
    assert not pocs.is_dark(horizon='observe')
    pocs.next_state = 'parking'
    for state in ['parking', 'parked', 'housekeeping', 'sleeping', 'ready']:
        assert pocs.next_state == state
        pocs.goto_next_state()
        assert pocs.state == state


def test_ready_dome_status(pocs):
    '''
    Test if the dome is open after ready state.
    '''
    os.environ['POCSTIME'] = '2020-10-29 23:00:00'
    pocs.initialize()
    pocs.get_ready()
    pocs.next_state == 'ready'
    pocs.goto_next_state()
    assert pocs.observatory.dome.is_open


def test_parking_dome_status(pocs):
    '''
    Test if the dome is closed after parking state.
    '''
    os.environ['POCSTIME'] = '2020-10-29 23:00:00'
    pocs.initialize()
    pocs.get_ready()
    pocs.next_state = 'parking'
    pocs.goto_next_state()
    assert not pocs.observatory.dome.is_open


def test_sleeping_stop(pocs):
    '''
    Test if ready transitions to sleeping and then stops if still dark.
    '''
    os.environ['POCSTIME'] = '2020-10-29 13:00:00'
    pocs.initialize()
    pocs.get_ready()
    pocs._obs_run_retries = -1
    assert (not pocs.should_retry)
    # Make sure its dark
    assert pocs.is_dark(horizon='observe')
    # Get into the sleeping state
    pocs.next_state = 'parking'
    for state in ['parking', 'parked', 'taking_darks', 'housekeeping', 'sleeping']:
        assert pocs.next_state == state
        pocs.goto_next_state()


def test_ready_scheduling_1(pocs):
    '''
    Test if ready goes into observe if its dark enough.
    '''
    os.environ['POCSTIME'] = '2020-10-29 13:00:00'
    pocs.initialize()
    pocs.observatory.last_focus_time = current_time()
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert not pocs.observatory.coarse_focus_required
    assert pocs.is_dark(horizon='observe')
    assert pocs.next_state == 'scheduling'


def test_ready_scheduling_2(pocs):
    '''
    Test if ready goes into scheduling in the evening if focus is not required
    and its not dark enough to start observing but its dark enough to focus.
    '''
    os.environ['POCSTIME'] = '2020-04-29 08:40:00'
    pocs.set_config('simulator', ['camera', 'mount'])
    pocs.initialize()
    pocs.observatory.last_focus_time = current_time()
    assert not pocs.observatory.past_midnight
    assert not pocs.observatory.coarse_focus_required
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.next_state == 'scheduling'


@pytest.mark.skip("Need to update pyro camera code.")
def test_ready_coarse_focusing_scheduling(pocs):
    '''
    Test if ready goes into observe if its dark enough via coarse focusing.
    '''
    os.environ['POCSTIME'] = '2020-04-29 08:40:00'
    pocs.set_config('simulator', ['camera', 'mount', 'power', 'weather'])
    pocs.initialize()
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.is_dark(horizon='focus')
    assert pocs.observatory.coarse_focus_required
    for state in ['coarse_focusing', 'scheduling']:
        assert pocs.next_state == state
        pocs.goto_next_state()


@pytest.mark.skip("Need to update pyro camera code.")
def test_evening_setup(pocs):
    '''
    Test the states in the evening before observing starts.
    '''
    # Preconditions to ready state
    os.environ['POCSTIME'] = '2020-04-29 08:10:00'
    pocs.set_config('simulator', ['camera', 'mount', 'power'])
    assert pocs.observatory.coarse_focus_required
    assert not pocs.observatory.past_midnight
    assert not pocs.is_dark(horizon='observe')
    assert not pocs.is_dark(horizon='focus')
    assert pocs.is_dark(horizon='flat')
    # Run state machine from ready
    pocs.initialize()
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.next_state == 'twilight_flat_fielding'
    for state in ['twilight_flat_fielding', 'coarse_focusing', 'scheduling']:
        assert pocs.next_state == state
        if state == 'twilight_flat_fielding':
            assert not pocs.is_dark(horizon='focus')
            assert pocs.is_dark(horizon='flat')
        elif state == 'coarse_focusing':
            os.environ['POCSTIME'] = '2020-04-29 08:40:00'
            assert pocs.is_dark(horizon='focus')
            assert not pocs.is_dark(horizon='observe')
        pocs.goto_next_state()
        assert pocs.state == state


def test_morning_parking(pocs):
    '''
    Test morning transition between ready, flat fielding and parking.
    '''
    os.environ['POCSTIME'] = '2020-04-29 19:30:00'
    pocs.initialize()
    pocs.observatory.last_focus_time = current_time()
    pocs.set_config('simulator', ['camera', 'mount', 'weather', 'power'])
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.observatory.past_midnight
    assert not pocs.observatory.coarse_focus_required
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    for state in ['twilight_flat_fielding', 'parking']:
        assert pocs.next_state == state
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2020-04-29 20:00:00'
            assert pocs.is_dark(horizon='flat')
        pocs.goto_next_state()
        assert pocs.state == state


@pytest.mark.skip("Need to update pyro camera code.")
def test_morning_coarse_focusing_parking(pocs):
    '''
    Test morning transition between coarse focusing, flat fielding and parking.
    '''
    os.environ['POCSTIME'] = '2020-04-29 19:30:00'
    pocs.initialize()
    pocs.get_ready()
    pocs.set_config('simulator', ['camera', 'mount'])
    assert pocs.state == 'ready'
    assert pocs.observatory.past_midnight
    assert pocs.observatory.coarse_focus_required
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    for state in ['coarse_focusing', 'twilight_flat_fielding', 'parking']:
        assert pocs.next_state == state
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2020-04-29 20:00:00'
            assert pocs.is_dark(horizon='flat')
        pocs.goto_next_state()
        assert pocs.state == state
