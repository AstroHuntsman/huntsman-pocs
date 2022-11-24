from panoptes.utils.config.client import get_config
from huntsman.pocs.dome.musca import HuntsmanDome
from huntsman.pocs.dome.simulator import Dome
from panoptes.utils.library import load_module
from panoptes.pocs.utils.logger import get_logger

logger = get_logger()


def create_dome_from_config(config=None):
    """ Convenience function to create the Huntsman dome.
    Args:
        config (dict): The config. If None, get from config server.
    Returns:
        huntsman.pocs.dome.musca.HuntsmanDome: The dome instance.
    """
    if config is None:
        config = get_config()
    dome_config = config.get("dome", None)
    return HuntsmanDome(config=dome_config)


def create_dome_simulator(*args, **kwargs):
    dome_config = get_config('dome')

    logger.debug(f'Creating dome simulator.')

    dome = Dome(*args, **kwargs)
    logger.info(f'Created dome simulator.')

    return dome
