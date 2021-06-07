import pytest

from huntsman.pocs.scheduler.field import Field, CompoundField, DitheredField
from huntsman.pocs.scheduler.observation import base as obsbase
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation

from huntsman.pocs.utils.huntsman import create_huntsman_scheduler

from panoptes.utils.config.client import get_config, set_config
from panoptes.pocs.scheduler.constraint import AlreadyVisited


@pytest.fixture(scope="function")
def field_config_1():
    return {"name": "Wasp 33", "position": "02h26m51.0582s +37d33m01.733s"}


@pytest.fixture(scope="function")
def field_config_2():
    return {"name": "Fake target", "position": "03h26m52.0582s +35d33m01.733s"}


def test_observe_once_global():
    prev_observe_once_status = get_config('scheduler.constraints.observe_once',
                                          default=False)
    set_config('scheduler.constraints.observe_once', True)
    scheduler = create_huntsman_scheduler()

    is_set = False
    for constraint in scheduler.constraints:
        if isinstance(constraint, AlreadyVisited):
            is_set = True
            break

    try:
        assert is_set
    finally:
        set_config('scheduler.constraints.observe_once', prev_observe_once_status)


def test_field(field_config_1, field_config_2):

    field = Field(**field_config_1)
    assert field.name
    assert field.field_name

    del field_config_1["name"]
    with pytest.raises(TypeError):
        Field(**field_config_1)

    del field_config_2["position"]
    with pytest.raises(TypeError):
        Field(**field_config_2)


def test_compound_field(field_config_1, field_config_2):

    field = CompoundField("test", [field_config_1, field_config_2])
    assert len(field) == 2

    # Test indexing
    for i in range(len(field)):
        assert isinstance(field[i], Field)

    # Test iteration
    for f in field:
        assert isinstance(f, Field)


def test_dithered_field(field_config_1):

    field = DitheredField(n_positions=9, **field_config_1)

    assert isinstance(field, CompoundField)  # Inheritance

    assert len(field) == 9


def test_observation(field_config_1):

    field = Field(**field_config_1)
    obs = obsbase.Observation(field=field)

    assert isinstance(obs, obsbase.AbstractObservation)
    assert isinstance(obs.field, Field)
    assert not obs.set_is_finished


def test_compound_observation(field_config_1, field_config_2):

    field = CompoundField("test", [field_config_1, field_config_2])

    obs = obsbase.CompoundObservation(field=field, batch_size=1)
    assert isinstance(obs.field, Field)
    assert obs.field.name == field_config_1["name"]
    obs.mark_exposure_complete()
    assert obs.field.name == field_config_2["name"]
    obs.mark_exposure_complete()
    assert obs.field.name == field_config_1["name"]

    obs = obsbase.CompoundObservation(field=field, batch_size=2)
    assert isinstance(obs.field, Field)
    assert obs.field.name == field_config_1["name"]
    obs.mark_exposure_complete()
    assert obs.field.name == field_config_1["name"]
    obs.mark_exposure_complete()
    assert obs.field.name == field_config_2["name"]

    field = Field(**field_config_1)
    with pytest.raises(TypeError):
        obsbase.CompoundObservation(field=field)

    expected_exp = 4  # len(field_configs) * batch_size
    while obs.current_exp_num < expected_exp:
        assert not obs.set_is_finished
        obs.mark_exposure_complete()
    assert obs.set_is_finished


def test_dithered_observation(field_config_1):

    field = DitheredField(**field_config_1)

    obs = DitheredObservation(field)
    assert isinstance(obs.field, Field)

    field = Field(**field_config_1)
    with pytest.raises(TypeError):
        DitheredObservation(field)


def test_compound_dithered_observation(field_config_1, field_config_2):

    field_config_1["type"] = "huntsman.pocs.scheduler.field.DitheredField"
    field_config_1["dither_kwargs"] = dict(n_positions=9)

    field_config_2["type"] = "huntsman.pocs.scheduler.field.DitheredField"
    field_config_2["dither_kwargs"] = dict(n_positions=5)

    field = CompoundField("test", [field_config_1, field_config_2])
    for f in field:
        assert isinstance(f, DitheredField)

    obs = obsbase.CompoundObservation(field)
    assert isinstance(obs.field, Field)
    assert obs.field.name.startswith(field_config_1["name"])
    obs.mark_exposure_complete()

    assert isinstance(obs.field, Field)
    assert obs.field.name.startswith(field_config_2["name"])
    obs.mark_exposure_complete()

    assert isinstance(obs.field, Field)
    assert obs.field.name.startswith(field_config_1["name"])

    expected_exp = 9 * 2  # max(n_positions) * len(field_configs)
    while obs.current_exp_num < expected_exp:
        assert not obs.set_is_finished
        obs.mark_exposure_complete()
    assert obs.set_is_finished


def test_compound_dithered_observation_batch(field_config_1, field_config_2):

    field_config_1["type"] = "huntsman.pocs.scheduler.field.DitheredField"
    field_config_1["dither_kwargs"] = dict(n_positions=9)

    field_config_2["type"] = "huntsman.pocs.scheduler.field.DitheredField"
    field_config_2["dither_kwargs"] = dict(n_positions=5)

    field = CompoundField("test", [field_config_1, field_config_2])
    for f in field:
        assert isinstance(f, DitheredField)

    obs = obsbase.CompoundObservation(field, batch_size=2)

    for _ in ["a", "b"]:
        assert isinstance(obs.field, Field)
        assert obs.field.name.startswith(field_config_1["name"])
        obs.mark_exposure_complete()

    for _ in ["c", "d"]:
        assert isinstance(obs.field, Field)
        assert obs.field.name.startswith(field_config_2["name"])
        obs.mark_exposure_complete()

    assert obs.field.name.startswith(field_config_1["name"])

    expected_exp = 9 * 2 * 2  # max(n_positions) * len(field_configs) * batch_size
    while obs.current_exp_num < expected_exp:
        assert not obs.set_is_finished
        obs.mark_exposure_complete()
    assert obs.set_is_finished


def test_filter_names_per_camera(field_config_1):

    cam_name = "dslr.00"
    filter_names_per_camera = {cam_name: "deux"}

    field = Field(**field_config_1)
    obs = obsbase.Observation(field=field, filter_names_per_camera=filter_names_per_camera,
                              filter_name="one")

    obsc = obs.copy()
    obsc.filter_name = obsc.filter_names_per_camera[cam_name]
    assert obsc.filter_name == "deux"
    assert obs.filter_name == "one"
