import os
import pytest

from pocs.core import POCS
from pocs.utils.location import create_location_from_config
from pocs.scheduler import create_scheduler_from_config
from pocs.dome import create_dome_from_config
from pocs.mount import create_mount_from_config

from huntsman.camera import create_cameras_from_config
from huntsman.observatory import HuntsmanObservatory as Observatory


@pytest.fixture(scope='function')
def cameras(config_with_simulated_stuff):
    """Get the default cameras from the config."""
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


def test_ready_sleeping_ready(pocs):
    '''
    Test if ready transitions to sleeping via parking and then back to ready.
    '''
    pocs.initialize()
    pocs.get_ready()
    # Make sure its no longer dark
    pocs.config['simulator'] = [_ for _ in pocs.config['simulator'] if _ != 'night']
    os.environ['POCSTIME'] = '2016-08-13 23:00:00'
    assert(not pocs.is_dark(horizon='observe'))
    # Get into the sleeping state
    for state in ['parking', 'parked', 'housekeeping', 'sleeping', 'ready']:
        assert(pocs.next_state == state)
        pocs.goto_next_state()
        assert(pocs.state == state)
    pocs.power_down()


def test_ready_sleeping_error(pocs):
    '''
    Test if ready transitions to sleeping and then errors if still dark.
    '''
    pocs.initialize()
    pocs.get_ready()
    # Make sure its dark
    assert(pocs.is_dark(horizon='observe'))
    # Get into the sleeping state
    for state in ['parking', 'parked', 'housekeeping', 'sleeping']:
        assert(pocs.next_state == state)
        if state == 'sleeping':
            with pytest.raises(RuntimeError):
                pocs.goto_next_state()
        else:
            pocs.goto_next_state()
    pocs.power_down()


@pytest.mark.skip(reason="Waiting for PR merge.")
def test_ready_scheduling(pocs):
    '''
    Test if ready goes into observe if its dark enough.
    '''
    pocs.initialize()
    pocs.get_ready()
    assert(pocs.state == 'ready')
    assert(pocs.is_dark(horizon='observe'))
    assert(pocs.next_state == 'scheduling')
    pocs.power_down()


def test_ready_coarse_focusing_twilight_flat_fielding(pocs):
    '''
    Test if ready goes into twilight_flat_fielding after coarse_focusing in the morning.
    '''
    pocs.config['simulator'] = [_ for _ in pocs.config['simulator'] if _ != 'night']
    os.environ['POCSTIME'] = '2016-08-13 018:00:00'
    pocs.initialize()
    pocs.get_ready()
    assert(pocs.state == 'ready')
    assert(pocs.observatory.past_midnight())
    assert(not pocs.is_dark(horizon='observe'))
    assert(pocs.is_dark(horizon='focus'))
    for state in ['coarse_focusing', 'twilight_flat_fielding']:
        assert(pocs.next_state == state)
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2016-08-13 018:00:00'
            assert(pocs.is_dark(horizon='flat'))
        pocs.goto_next_state()
        assert(pocs.state == state)
    assert(pocs.next_state == 'twilight_flat_fielding')
    pocs.power_down()


def test_ready_twilight_flat_fielding_coarse_focusing(pocs):
    '''
    Test if ready goes into coarse_focusing after twilight_flat_fielding in the evening.
    '''
    pocs.config['simulator'] = [_ for _ in pocs.config['simulator'] if _ != 'night']
    os.environ['POCSTIME'] = '2016-08-13 05:00:00'
    pocs.initialize()
    pocs.get_ready()
    assert(pocs.state == 'ready')
    assert(pocs.observatory.require_coarse_focus())
    assert(not pocs.is_dark(horizon='observe'))
    assert(not pocs.is_dark(horizon='focus'))
    assert(not pocs.observatory.past_midnight())
    assert(pocs.next_state == 'twilight_flat_fielding')
    for state in ['twilight_flat_fielding', 'coarse_focusing']:
        assert(pocs.next_state == state)
        if state == 'twilight_flat_fielding':
            os.environ['POCSTIME'] = '2016-08-13 018:00:00'
            assert(pocs.is_dark(horizon='flat'))
        elif state == 'coarse_focusing':
            os.environ['POCSTIME'] = '2016-08-13 018:00:00'
            assert(pocs.is_dark(horizon='focus'))
        pocs.goto_next_state()
        assert(pocs.state == state)
    pocs.power_down()


@pytest.mark.skip(reason="Waiting for PR merge.")
def test_coarse_focusing_scheduling(pocs):
    '''
    Test if ready goes into coarse_focusing after twilight_flat_fielding in the evening.
    '''
    os.environ['POCSTIME'] = '2016-08-13 05:00:00'
    pocs.initialize()
    pocs.get_ready()
    assert(pocs.state == 'ready')
    assert(pocs.observatory.require_coarse_focus())
    assert(not pocs.is_dark(horizon='observe'))
    assert(pocs.next_state == 'scheduling')
    for state in ['scheduling']:
        pocs.next_state = state
        pocs.goto_next_state()
        assert(pocs.state == state)
    pocs.power_down()
