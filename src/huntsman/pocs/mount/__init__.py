from contextlib import suppress

from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.utils.logger import get_logger
from panoptes.utils import error
from panoptes.utils.library import load_module
from panoptes.utils.config.client import get_config, set_config

logger = get_logger()


def create_mount_simulator(mount_info=None,
                           earth_location=None,
                           db_type='memory',
                           *args, **kwargs):
    # Remove mount simulator
    current_simulators = get_config('simulator', default=[])
    logger.warning(f'Current simulators: {current_simulators}')
    with suppress(ValueError):
        current_simulators.remove('mount')

    mount_config = mount_info or {
        'model': 'Mount Simulator',
        'driver': 'huntsman.pocs.mount.simulator',
        'serial': {
            'port': '/dev/FAKE'
        }
    }

    # Set mount device info to simulator
    set_config('mount', mount_config)

    earth_location = earth_location or create_location_from_config()['earth_location']

    logger.debug(f"Loading mount driver: {mount_config['driver']}")
    try:
        module = load_module(f"{mount_config['driver']}")
    except error.NotFound as e:
        raise error.MountNotFound(f'Error loading mount module: {e!r}')

    mount_obj = module.Mount(earth_location, db_type=db_type, *args, **kwargs)

    logger.success(f"{mount_config['driver'].title()} mount created")

    return mount_obj
