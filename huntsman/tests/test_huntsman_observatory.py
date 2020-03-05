import os
import pytest


from huntsman.observatory import HuntsmanObservatory


def test_bad_observatory(config):
    del os.environ['HUNTSMAN_POCS']

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        HuntsmanObservatory()
    assert pytest_wrapped_e.type == SystemExit
    assert pytest_wrapped_e.value.code == 'Must set HUNTSMAN_POCS variable'
