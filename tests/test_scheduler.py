import pytest

from huntsman.pocs.scheduler.field import Field, CompoundField, DitheredField
from huntsman.pocs.scheduler.observation import base as obsbase


@pytest.fixture(scope="function")
def field_config_1():
    return {"name": "Wasp 33", "position": "02h26m51.0582s +37d33m01.733s"}


@pytest.fixture(scope="function")
def field_config_2():
    return {"name": "Fake target", "position": "03h26m52.0582s +35d33m01.733s"}


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
    obs.exposure_list["a"] = None
    assert obs.field.name == field_config_2["name"]
    obs.exposure_list["b"] = None
    assert obs.field.name == field_config_1["name"]

    obs = obsbase.CompoundObservation(field=field, batch_size=2)
    assert isinstance(obs.field, Field)
    assert obs.field.name == field_config_1["name"]
    obs.exposure_list["a"] = None
    assert obs.field.name == field_config_1["name"]
    obs.exposure_list["b"] = None
    assert obs.field.name == field_config_2["name"]

    field = Field(**field_config_1)
    with pytest.raises(TypeError):
        obsbase.CompoundObservation(field=field)
