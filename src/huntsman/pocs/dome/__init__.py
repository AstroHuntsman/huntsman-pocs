from panoptes.utils.config.client import get_config
from huntsman.pocs.dome.musca import HuntsmanDome


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
