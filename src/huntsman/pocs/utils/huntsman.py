from panoptes.utils.config.client import get_config

from panoptes.pocs.scheduler import create_scheduler_from_config
from panoptes.pocs.mount import create_mount_from_config

from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.dome import create_dome_from_config
from huntsman.pocs.core import HuntsmanPOCS


def create_huntsman_observatory(with_dome=False, cameras=None, mount=None, scheduler=None,
                                dome=None, config=None, **kwargs):
    """ Convenience function to create the observatory instance in one line.
    Args:
        with_dome (bool, optional): If True, add a dome to the observatory. Default False (safe).
        cameras (OrderedDict, optional): The cameras. If None (default), will create from config.
        mount (Mount, optional): The Mount object. If None (default), will create from config.
        scheduler (Scheduler, optional): The scheduler. If None (default), will create from config.
        dome (Dome, optional): The Dome. If None (default) and with_dome=True, will create from
            config.
        **kwargs: Parsed to the new `HuntsmanObservatory` instance.
    Returns:
        `huntsman.pocs.observatory.HuntsmanObservatory`: The observatory instance.
    """
    if config is None:
        config = get_config()

    if cameras is None:
        cameras = create_cameras_from_config(config=config)

    if mount is None:
        mount = create_mount_from_config()   # TODO: Parse config
    mount.initialize()

    if scheduler is None:
        scheduler = create_scheduler_from_config()  # TODO: Parse config

    if with_dome:
        if dome is None:
            dome = create_dome_from_config(config=config)
    else:
        dome = None

    # Create and return the observatory
    observatory = HuntsmanObservatory(cameras=cameras, mount=mount, scheduler=scheduler,
                                      dome=dome, config=config, **kwargs)
    return observatory


def create_huntsman_pocs(observatory=None, simulators=['power', ], **kwargs):
    """ Convenience function to create and initialise a POCS instance.
    Args:
        observatory (Observatory, optional): If given, use this observatory. Else, create from
            config.
        simulators (list, optional): The list of simulators to parse to the POCS instance.
        **kwargs: Parsed to `create_huntsman_observatory` if observatory not provided.
    Returns:
        `huntsman.pocs.observatory.HuntsmanObservatory`: The observatory instance.
    """
    if observatory is None:
        observatory = create_huntsman_observatory(**kwargs)

    huntsman = HuntsmanPOCS(observatory=observatory, simulators=simulators)
    huntsman.initialize()

    return huntsman
