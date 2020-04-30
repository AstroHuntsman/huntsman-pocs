import os
import pytest

from pocs.core import POCS
from pocs import utils
from pocs.utils.location import create_location_from_config
from pocs.scheduler import create_scheduler_from_config
from pocs.dome import create_dome_from_config
from pocs.mount import create_mount_from_config

from huntsman.camera import create_cameras_from_config
from huntsman.observatory import HuntsmanObservatory as Observatory


@pytest.fixture(scope='function')
def cameras(config_with_simulated_stuff):
    return create_cameras_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def scheduler(config_with_simulated_stuff):
    site_details = create_location_from_config(config_with_simulated_stuff)
    return create_scheduler_from_config(config_with_simulated_stuff,
                                        observer=site_details['observer'])


@pytest.fixture(scope='function')
def dome(config_with_simulated_stuff):
    return create_dome_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def mount(config_with_simulated_stuff):
    return create_mount_from_config(config_with_simulated_stuff)


@pytest.fixture(scope='function')
def observatory(config_with_simulated_stuff, db_type, cameras, scheduler, dome, mount):
    observatory = Observatory(config=config_with_simulated_stuff, cameras=cameras,
                              scheduler=scheduler, dome=dome, mount=mount, db_type=db_type)
    return observatory


@pytest.fixture(scope='function')
def pocs(config_with_simulated_stuff, observatory):
    pocs = POCS(observatory, run_once=True, config=config_with_simulated_stuff)
    yield pocs
    pocs.power_down()

# ==============================================================================


def test_parking_ready(pocs):
    '''
    Test if the parking state transitions back into ready.
    '''
    pocs.initialize()
    pocs.get_ready()
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    os.environ['POCSTIME'] = '2020-04-29 23:00:00'
    assert not pocs.is_dark(horizon='observe')
    pocs.next_state = 'parking'
    for state in ['parking', 'parked', 'housekeeping', 'sleeping', 'ready']:
        assert pocs.next_state == state
        pocs.goto_next_state()
        assert pocs.state == state


def test_sleeping_stop(pocs):
    '''
    Test if ready transitions to sleeping and then stops if still dark.
    '''
    pocs.initialize()
    pocs.get_ready()
    # Make sure its dark
    assert pocs.is_dark(horizon='observe')
    # Get into the sleeping state
    pocs.next_state = 'parking'
    for state in ['parking', 'parked', 'housekeeping', 'sleeping']:
        assert pocs.next_state == state
        pocs.goto_next_state()
        if state == 'sleeping':
            assert pocs._do_states is False


def test_ready_scheduling_1(pocs):
    '''
    Test if ready goes into observe if its dark enough.
    '''
    pocs.initialize()
    pocs.observatory.last_focus_time = utils.current_time()
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert not pocs.observatory.require_coarse_focus
    assert pocs.is_dark(horizon='observe')
    assert pocs.next_state == 'scheduling'


def test_ready_scheduling_2(pocs):
    '''
    Test if ready goes into scheduling in the evening if focus is not required
    and its not dark enough to start observing but its dark enough to focus.
    '''
    os.environ['POCSTIME'] = '2020-04-29 08:40:00'
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    pocs.initialize()
    pocs.observatory.last_focus_time = utils.current_time()
    assert not pocs.observatory.past_midnight
    assert not pocs.observatory.require_coarse_focus
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.next_state == 'scheduling'


def test_ready_coarse_focusing_scheduling(pocs):
    '''
    Test if ready goes into observe if its dark enough via coarse focusing.
    '''
    pocs.initialize()
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.is_dark(horizon='observe')
    assert pocs.observatory.require_coarse_focus
    for state in ['coarse_focusing', 'scheduling']:
        assert pocs.next_state == state
        pocs.goto_next_state()


def test_evening_setup(pocs):
    '''
    Test the states in the evening before observing starts.
    '''
    # Preconditions to ready state
    os.environ['POCSTIME'] = '2020-04-29 08:10:00'
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    assert pocs.observatory.require_coarse_focus
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
    pocs.observatory.last_focus_time = utils.current_time()
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    pocs.get_ready()
    assert pocs.state == 'ready'
    assert pocs.observatory.past_midnight
    assert not pocs.observatory.require_coarse_focus
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    for state in ['twilight_flat_fielding', 'parking']:
        assert pocs.next_state == state
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2020-04-29 20:00:00'
            assert pocs.is_dark(horizon='flat')
        pocs.goto_next_state()
        assert pocs.state == state


def test_morning_coarse_focusing_parking(pocs):
    '''
    Test morning transition between coarse focusing, flat fielding and parking.
    '''
    os.environ['POCSTIME'] = '2020-04-29 19:30:00'
    pocs.initialize()
    pocs.get_ready()
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    assert pocs.state == 'ready'
    assert pocs.observatory.past_midnight
    assert pocs.observatory.require_coarse_focus
    assert not pocs.is_dark(horizon='observe')
    assert pocs.is_dark(horizon='focus')
    for state in ['coarse_focusing', 'twilight_flat_fielding', 'parking']:
        assert pocs.next_state == state
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2020-04-29 20:00:00'
            assert pocs.is_dark(horizon='flat')
        pocs.goto_next_state()
        assert pocs.state == state
