import os
import pytest
import time
import threading

from astropy import units as u

from pocs import hardware
from pocs.base import PanBase
from pocs.core import POCS
from pocs.utils import error
from pocs.utils import CountdownTimer

from huntsman.camera import create_cameras_from_config
from huntsman.camera.pyro import Camera as PyroCamera
from huntsman.observatory import HuntsmanObservatory as Observatory


def wait_for_running(sub, max_duration=90):
    """Given a message subscriber, wait for a RUNNING message."""
    timeout = CountdownTimer(max_duration)
    while not timeout.expired():
        topic, msg_obj = sub.receive_message()
        if msg_obj and 'RUNNING' == msg_obj.get('message'):
            return True
    return False


def wait_for_state(sub, state, max_duration=90):
    """Given a message subscriber, wait for the specified state."""
    timeout = CountdownTimer(max_duration)
    while not timeout.expired():
        topic, msg_obj = sub.receive_message()
        if topic == 'STATUS' and msg_obj and msg_obj.get('state') == state:
            return True
    return False


@pytest.fixture(scope='function')
def cameras(config):
    """Get the default cameras from the config."""
    config['simulator'] = ['camera']
    return create_cameras_from_config(config)


@pytest.fixture(scope='function')
def observatory(config, cameras):
    observatory = Observatory(
        config=config,
        cameras=cameras,
        simulator=['all'],
        ignore_local_config=True
    )
    return observatory


@pytest.fixture(scope='function')
def pocs(config, observatory):
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'

    pocs = POCS(observatory,
                run_once=True,
                config=config,
                simulator=['all'],
                ignore_local_config=True)

    yield pocs

    pocs.power_down()


def test_check_config1(config):
    del config['mount']
    base = PanBase()
    with pytest.raises(SystemExit):
        base._check_config(config)


def test_check_config2(config):
    del config['directories']
    base = PanBase()
    with pytest.raises(SystemExit):
        base._check_config(config)


def test_check_config3(config):
    del config['state_machine']
    base = PanBase()
    with pytest.raises(SystemExit):
        base._check_config(config)


def test_bad_pandir_env(pocs):
    pandir = os.getenv('PANDIR')
    os.environ['PANDIR'] = '/foo/bar'
    with pytest.raises(SystemExit):
        pocs.check_environment()
    os.environ['PANDIR'] = pandir


def test_bad_pocs_env(pocs):
    pocs_dir = os.getenv('POCS')
    os.environ['POCS'] = '/foo/bar'
    with pytest.raises(SystemExit):
        pocs.check_environment()
    os.environ['POCS'] = pocs_dir


def test_make_log_dir(pocs):
    log_dir = "{}/logs".format(os.getcwd())
    assert os.path.exists(log_dir) is False

    old_pandir = os.environ['PANDIR']
    os.environ['PANDIR'] = os.getcwd()
    pocs.check_environment()

    assert os.path.exists(log_dir) is True
    os.removedirs(log_dir)

    os.environ['PANDIR'] = old_pandir


def test_simple_simulator(pocs):
    assert isinstance(pocs, POCS)


def test_not_initialized(pocs):
    assert pocs.is_initialized is not True


def test_run_without_initialize(pocs):
    with pytest.raises(AssertionError):
        pocs.run()


def test_initialization(pocs):
    pocs.initialize()
    assert pocs.is_initialized


def test_bad_state_machine_file():
    with pytest.raises(error.InvalidConfig):
        POCS.load_state_table(state_table_name='foo')


def test_load_bad_state(pocs):
    with pytest.raises(error.InvalidConfig):
        pocs._load_state('foo')


def test_default_lookup_trigger(pocs):
    pocs.state = 'parking'
    pocs.next_state = 'parking'

    assert pocs._lookup_trigger() == 'set_park'

    pocs.state = 'foo'

    assert pocs._lookup_trigger() == 'parking'


def test_free_space(pocs):
    assert pocs.has_free_space() is True

    # Test something ridiculous
    assert pocs.has_free_space(required_space=1e9 * u.gigabyte) is False


def test_is_dark_simulator(pocs):
    pocs.initialize()
    pocs.config['simulator'] = ['camera', 'mount', 'weather', 'night']
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'
    assert pocs.is_dark() is True

    os.environ['POCSTIME'] = '2016-08-13 23:00:00'
    assert pocs.is_dark() is True


def test_is_dark_no_simulator_01(pocs):
    pocs.initialize()
    pocs.config['simulator'] = ['camera', 'mount', 'weather']
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'
    assert pocs.is_dark() is True


def test_is_dark_no_simulator_02(pocs):
    pocs.initialize()
    pocs.config['simulator'] = ['camera', 'mount', 'weather']
    os.environ['POCSTIME'] = '2016-08-13 23:00:00'
    assert pocs.is_dark() is False


def test_is_weather_safe_simulator(pocs):
    pocs.initialize()
    pocs.config['simulator'] = ['camera', 'mount', 'weather']
    assert pocs.is_weather_safe() is True


def test_is_weather_safe_no_simulator(pocs, db):
    pocs.initialize()
    pocs.config['simulator'] = ['camera', 'mount', 'night']

    # Set a specific time
    os.environ['POCSTIME'] = '2016-08-13 23:00:00'

    # Insert a dummy weather record
    db.insert_current('weather', {'safe': True})
    assert pocs.is_weather_safe() is True

    # Set a time 181 seconds later
    os.environ['POCSTIME'] = '2016-08-13 23:05:01'
    assert pocs.is_weather_safe() is False


def test_pyro_camera(config, camera_server):
    conf = config.copy()
    conf['cameras'] = {'distributed_cameras': True}
    simulator = hardware.get_all_names(without=['camera'])
    conf['simulator'] = simulator
    cameras = create_cameras_from_config(conf)
    obs = Observatory(cameras=cameras,
                      config=conf,
                      simulator=simulator,
                      ignore_local_config=True)
    assert len(obs.cameras) == 1
    assert 'camera.simulator.001' in obs.cameras
    assert isinstance(obs.cameras['camera.simulator.001'], PyroCamera)
    assert obs.cameras['camera.simulator.001'].is_connected


def test_run_wait_until_safe(observatory, cmd_publisher, msg_subscriber):
    os.environ['POCSTIME'] = '2016-09-09 10:00:00'

    observatory.db.insert_current('weather', {'safe': False})

    def start_pocs():
        observatory.logger.info('start_pocs ENTER')
        # Remove weather simulator, else it would always be safe.
        observatory.config['simulator'] = hardware.get_all_names(without=['weather'])

        pocs = POCS(observatory, messaging=True, safe_delay=5)

        pocs.observatory.scheduler.clear_available_observations()
        pocs.observatory.scheduler.add_observation({'name': 'KIC 8462852',
                                                    'position': '20h06m15.4536s +44d27m24.75s',
                                                    'priority': '100',
                                                    'exp_time': 2,
                                                    'min_nexp': 2,
                                                    'exp_set_size': 2,
                                                    })

        pocs.initialize()
        pocs.logger.info('Starting observatory run')
        assert pocs.is_weather_safe() is False
        pocs.logger.info('Sending RUNNING message')
        pocs.send_message('RUNNING')
        pocs.run(run_once=True, exit_when_done=True)
        assert pocs.observatory.is_weather_safe() is True
        pocs.power_down()
        pocs.observatory.logger.info('start_pocs EXIT')

    pocs_thread = threading.Thread(target=start_pocs, daemon=True)
    pocs_thread.start()

    try:
        # Wait for the RUNNING message,
        assert wait_for_running(msg_subscriber)
        observatory.logger.info('Got RUNNING message')

        time.sleep(5)
        # Insert a dummy weather record to break wait
        observatory.db.insert_current('weather', {'safe': True})

        assert wait_for_state(msg_subscriber, 'scheduling')
    finally:
        cmd_publisher.send_message('POCS-CMD', 'shutdown')
        pocs_thread.join(timeout=30)

    assert pocs_thread.is_alive() is False


def test_unsafe_park(pocs):
    pocs.initialize()
    assert pocs.is_initialized is True
    os.environ['POCSTIME'] = '2016-08-13 13:00:00'
    assert pocs.state == 'sleeping'
    pocs.get_ready()
    assert pocs.state == 'ready'
    pocs.schedule()
    assert pocs.state == 'scheduling'

    # My time goes fast...
    os.environ['POCSTIME'] = '2016-08-13 23:00:00'
    pocs.config['simulator'] = hardware.get_all_names(without=['night'])
    assert pocs.is_safe() is False

    assert pocs.state == 'parking'
    pocs.set_park()
    pocs.clean_up()
    pocs.power_down()


def test_power_down_while_running(pocs):
    assert pocs.connected is True
    pocs.initialize()
    pocs.get_ready()
    assert pocs.state == 'ready'
    pocs.power_down()

    assert pocs.state == 'parked'
    assert pocs.connected is False


def test_run_no_targets_and_exit(pocs):
    os.environ['POCSTIME'] = '2016-09-09 10:00:00'

    pocs.config['simulator'] = hardware.get_all_names()
    pocs.state = 'sleeping'

    pocs.initialize()
    pocs.observatory.scheduler.clear_available_observations()
    pocs.observatory.scheduler._fields_file = None
    pocs.observatory.scheduler._fields_list = None
    assert pocs.is_initialized is True

    pocs.observatory.take_flat_fields = False
    assert pocs.observatory.take_flat_fields is False
    pocs.run(exit_when_done=True, run_once=True)
    assert pocs.state == 'sleeping'


def test_run(pocs):
    os.environ['POCSTIME'] = '2016-09-09 10:00:00'
    pocs.config['simulator'] = hardware.get_all_names()
    pocs.state = 'sleeping'
    pocs._do_states = True

    pocs.observatory.scheduler.clear_available_observations()
    pocs.observatory.scheduler.add_observation({'name': 'KIC 8462852',
                                                        'position': '20h06m15.4536s +44d27m24.75s',
                                                        'priority': '1000',
                                                        'exp_time': 2,
                                                        'min_nexp': 2,
                                                        'exp_set_size': 2,
                                                })

    pocs.initialize()
    assert pocs.is_initialized is True

    pocs.observatory.take_flat_fields = False
    pocs.run(exit_when_done=True, run_once=True)
    assert pocs.state == 'sleeping'


def test_run_power_down_interrupt(observatory, msg_subscriber, cmd_publisher):
    def start_pocs():
        pocs = POCS(observatory, messaging=True)
        pocs.initialize()
        pocs.observatory.scheduler.fields_list = [{'name': 'KIC 8462852',
                                                   'position': '20h06m15.4536s +44d27m24.75s',
                                                   'priority': '100',
                                                   'exp_time': 2,
                                                   'min_nexp': 1,
                                                   'exp_set_size': 1,
                                                   }]
        pocs.logger.info('Starting observatory run')
        pocs.run()

    pocs_thread = threading.Thread(target=start_pocs, daemon=True)
    pocs_thread.start()

    try:
        assert wait_for_state(msg_subscriber, 'scheduling')
    finally:
        cmd_publisher.send_message('POCS-CMD', 'shutdown')
        pocs_thread.join(timeout=30)

    assert pocs_thread.is_alive() is False
