import pytest

from astropy.time import Time
from huntsman.utils.too.grav_wave.grav_wave import GravityWaveEvent
from scripts.gcn_processing import get_skymap


@pytest.fixture
def sample_fits():
    return 'https://dcc.ligo.org/P1500071/public/10458_bayestar.fits.gz'


@pytest.fixture
def sample_time():
    time = Time()
    return time


def test_define_tiles_all(sample_fits):
    skymap, header = get_skymap(sample_fits)
    header['NOTICE'] = 'test_define_tiles_all'

    grav_wave = GravityWaveEvent(skymap=skymap,
                                 header=header,
                                 alert_pocs=False)

    tiles = grav_wave.define_tiles(grav_wave.catalog[0], 'tl_tr_bl_br_c')

    assert len(tiles) == 5


def test_probability_redshift_calc(sample_fits):
    skymap, header = get_skymap(sample_fits)
    header['NOTICE'] = 'test_probability_redshift_calc'

    grav_wave = GravityWaveEvent(skymap=skymap,
                                 header=header,
                                 alert_pocs=False)

    prob, redshift, dist = grav_wave.get_prob_red_dist(grav_wave.catalog, grav_wave.event_data)

    assert (len(prob) > 0) and (len(redshift) == len(dist)) and (len(prob) == len(dist))


@pytest.mark.xfail(reason="Known bug, issue #36")
def test_get_good_tiles(sample_fits):
    skymap, header = get_skymap(sample_fits)
    header['NOTICE'] = 'test_get_good_tiles'

    selection_criteria = {'name': 'one_loop', 'max_tiles': 5}

    grav_wave = GravityWaveEvent(skymap=skymap,
                                 header=header,
                                 percentile=99.5,
                                 selection_criteria=selection_criteria,
                                 alert_pocs=False)

    tiles = grav_wave.tile_sky()

    max_score = 0

    for tile in tiles:

        if tile['properties']['score'] > max_score:
            max_score = tile['properties']['score']

    assert tiles[0]['properties']['score'] == max_score


@pytest.mark.xfail(reason="Known bug, issue #36")
def test_tile_sky(sample_fits):
    skymap, header = get_skymap(sample_fits)
    header['NOTICE'] = 'test_tile_sky'

    selection_criteria = {'name': '5_tiles', 'max_tiles': 5}

    grav_wave = GravityWaveEvent(skymap=skymap,
                                 header=header,
                                 percentile=99.5,
                                 selection_criteria=selection_criteria,
                                 alert_pocs=False)

    tiles = grav_wave.tile_sky()

    assert len(tiles) == 5
