import os

from astropy import units as u

from panoptes.utils import error
from panoptes.utils.config.client import get_config
from panoptes.utils.library import load_module
from panoptes.utils import horizon as horizon_utils

from panoptes.pocs.utils.location import create_location_from_config
from panoptes.pocs.scheduler.constraint import Altitude

from huntsman.pocs.utils.logger import get_logger
from huntsman.pocs.camera.utils import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.dome import create_dome_from_config
from huntsman.pocs.core import HuntsmanPOCS
from huntsman.pocs.scheduler.constraint import SunAvoidance
from panoptes.pocs.scheduler.constraint import AlreadyVisited
from huntsman.pocs.scheduler.constraint import MoonAvoidance as HuntsmanMoonAvoidance
from huntsman.pocs.mount.bisque import create_mount


def create_huntsman_scheduler(observer=None, logger=None, *args, **kwargs):
    """ Sets up the scheduler that will be used by the observatory.
    This overrides the default POCS `create_scheduler_from_config` method by:
    - Removing Duration constraint.
    - Using Huntsman MoonAvoidance constraint.
    - Using Huntsman logger.
    """
    if not logger:
        logger = get_logger()

    scheduler_config = get_config('scheduler', default=None)

    if not scheduler_config:
        raise RuntimeError("No scheduler in config")
    logger.info(f'scheduler_config: {scheduler_config!r}')

    site_details = create_location_from_config()
    observer = site_details['observer']

    scheduler_type = scheduler_config.get('type', 'dispatch')

    # Read the targets from the file
    fields_file = scheduler_config.get('fields_file', 'simple.yaml')
    fields_path = os.path.join(get_config('directories.fields'), fields_file)
    logger.debug(f'Creating scheduler: {fields_path}')

    if os.path.exists(fields_path):

        try:
            # Load the required module
            module = load_module(f'{scheduler_type}')

            obstruction_list = get_config('location.obstructions', default=[])
            default_horizon = get_config('location.horizon', default=30 * u.degree)

            horizon_line = horizon_utils.Horizon(obstructions=obstruction_list,
                                                 default_horizon=default_horizon.value)

            # Simple constraint for now
            constraints = [Altitude(horizon=horizon_line),
                           HuntsmanMoonAvoidance(),
                           SunAvoidance()]

            # add global observe each target once constraint
            if get_config('constraints.observe_once', default=False):
                constraints.insert(0, AlreadyVisited())

            # Create the Scheduler instance
            scheduler = module.Scheduler(observer, fields_file=fields_path, constraints=constraints,
                                         *args, **kwargs)
            logger.debug("Scheduler created")
        except error.NotFound as e:
            raise error.NotFound(msg=e)
    else:
        raise error.NotFound(msg=f"Fields file does not exist: fields_file={fields_file!r}")

    return scheduler


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
        mount = create_mount()   # TODO: Parse config
    mount.initialize()

    if scheduler is None:
        scheduler = create_huntsman_scheduler()  # TODO: Parse config

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
