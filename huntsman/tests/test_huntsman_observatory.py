import os
import pytest


from huntsman.observatory import HuntsmanObservatory


def test_bad_observatory(config):
    del os.environ['HUNTSMAN_POCS']

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        obs = HuntsmanObservatory()
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 'Must set HUNTSMAN_POCS variable'


@pytest.fixture(scope='function')
def cameras(config):
    """Get the default cameras from the config."""
    return create_cameras_from_config(config)


@pytest.fixture(scope='function')
def observatory(config, cameras):
    observatory = Observatory(
        config=config,
        cameras=cameras,
        simulator=['all'],
    )
    yield observatory
