import os
import pytest

from panoptes.pocs.core import POCS
from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.dome import create_dome_from_config
from panoptes.pocs.mount import create_mount_from_config

from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory as Observatory


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

def test_bad_observatory(config):
    huntsman_pocs = os.environ['HUNTSMAN_POCS']
    try:
        del os.environ['HUNTSMAN_POCS']
        with pytest.raises(SystemExit) as pytest_wrapped_e:
            Observatory()
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 'Must set HUNTSMAN_POCS variable'
    finally:
        os.environ['HUNTSMAN_POCS'] = huntsman_pocs


def test_take_flat_fields(pocs):
    """

    """
    os.environ['POCSTIME'] = '2020-04-29 08:10:00'
    pocs.config['simulator'] = [s for s in pocs.config['simulator'] if s != 'night']
    pocs.initialize()
    assert not pocs.observatory.past_midnight
    assert not pocs.is_dark(horizon='observe')
    assert not pocs.is_dark(horizon='focus')
    assert pocs.is_dark(horizon='flat')
    pocs.get_ready()
    pocs.observatory.take_flat_fields(alt=60, az=90, max_num_exposures=1,
                                      tolerance=0.5)
