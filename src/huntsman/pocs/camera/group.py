import time

from functools import partial
from collections import abc
from multiprocessing.pool import ThreadPool

from panoptes.utils import error
from panoptes.utils.time import wait_for_events

from panoptes.pocs.base import PanBase


def dispatch_parallel(function, camera_names, **kwargs):
    """ Run a function in parallel using a thread pool.
    Args:
        function (Function): The function to run.
        camera_names (list): The list of camera names to process.
        **kwargs: Parsed to function.
    Returns:
        dict: Dict of cam_name: result pairs.
    """
    camera_names = list(camera_names)

    func = partial(function, **kwargs)

    with ThreadPool(len(camera_names)) as pool:
        results = pool.map(func, camera_names)

    return {k: v for k, v in zip(camera_names, results)}


class CameraGroup(PanBase):

    def __init__(self, cameras, **kwargs):
        super().__init__(**kwargs)
        self.cameras = cameras

    def __str__(self):
        return f"CameraGroup with {len(self.cameras)} cameras"

    @property
    def camera_names(self):
        return list(self.cameras.keys())

    def activate_camera_cooling(self):
        """ Activate camera cooling for all cameras. """
        self.logger.debug('Activating camera cooling for all cameras.')
        for cam in self.cameras.values():
            if cam.is_cooled_camera:
                cam.cooling_enabled = True

    def deactivate_camera_cooling(self):
        """ Deactivate camera cooling for all cameras. """
        self.logger.debug('Deactivating camera cooling for all cameras.')
        for cam in self.cameras.values():
            if cam.is_cooled_camera:
                cam.cooling_enabled = False

    def wait_until_ready(self, sleep=60, max_attempts=5):
        """ Make sure cameras are all cooled and ready.
        Arguments:
            sleep (float): Time in seconds to sleep between checking readiness. Default 60.
            max_attempts (int): Maximum number of ready checks. See `require_all_cameras`.
        """
        self.logger.info(f"Preparing {len(self.cameras)} cameras.")

        # Make sure camera cooling is enabled
        self.activate_camera_cooling()

        # Wait for cameras to be ready
        n_cameras = len(self.cameras)
        num_cameras_ready = 0
        failed_cameras = []

        self.logger.debug('Waiting for cameras to be ready.')
        for i in range(1, max_attempts + 1):

            num_cameras_ready = 0
            for cam_name, cam in self.cameras.items():

                if cam.is_ready:
                    num_cameras_ready += 1
                    continue

                # If max attempts have been reached...
                if i == max_attempts:
                    self.logger.error(f'Max attempts reached while waiting for {cam_name}.')
                    failed_cameras.append(cam_name)

            # Terminate loop if all cameras are ready
            self.logger.debug(f'Number of ready cameras after {i} of {max_attempts} checks:'
                              f' {num_cameras_ready} of {n_cameras}.')
            if num_cameras_ready == n_cameras:
                self.logger.debug('All cameras are ready.')
                break

            elif i < max_attempts:
                self.logger.debug('Not all cameras are ready yet, '
                                  f'waiting another {sleep} seconds before checking again.')
                time.sleep(sleep)

        if not all([c.is_ready for c in self.cameras.values()]):
            self.logger.warning("Not all cameras are ready. Continuing anyway.")

        return failed_cameras

    def take_observation(self, observation, headers=None):
        """ Take observation on all cameras in group.
        Args:
            observation (Observation): The observation object.
            headers (dict, optional): Header items.
        Returns:
            dict: Dict of cam_name: threading.Event.
        """
        self.logger.info(f"Taking observation {observation} for {self}.")

        # Define function to start exposures in parallel
        def func(cam_name):
            camera = self.cameras[cam_name]

            obs_kwargs = {"headers": headers}

            # Take the exposure and catch errors
            try:
                event = camera.take_observation(observation, **obs_kwargs)
            except error.PanError as err:
                self.logger.error(f"{err!r}")
                return None

            return event

        # Start the exposures and return events
        return dispatch_parallel(func, self.camera_names)

    def filterwheel_move_to(self, filter_name=None, dark_position=False):
        """Move all the filterwheels to a given filter
        Args:
            filter_name (str or dict, optional): Name of the filter where filterwheels will be
                moved to. If a dict, should be specified in camera_name: filter_name pairs.
            dark_position (bool, optional): If True, ignore filter_name arg and move all FWs to
                their dark position. Default: False.
            camera_names (list, optional): List of camera names to be used.
                Default to `None`, which uses all cameras.
        """
        # We only care about cameras that have FWs here
        cameras = {k: v for k, v in self.cameras.items() if v.has_filterwheel}

        filterwheel_events = dict()

        if dark_position:
            self.logger.debug('Moving all filterwheels to dark position.')
            for camera in cameras.values():
                filterwheel_events[camera] = camera.filterwheel.move_to_dark_position()

        elif filter_name is None:
            raise ValueError("filter_name must not be None.")

        else:
            self.logger.debug(f'Moving filterwheels to {filter_name} filter.')
            for cam_name, camera in cameras.items():

                if isinstance(filter_name, dict):
                    fn = filter_name[cam_name]
                else:
                    fn = filter_name

                filterwheel_events[camera] = camera.filterwheel.move_to(fn)

        # Wait for move to complete
        wait_for_events(list(filterwheel_events.values()))

        self.logger.debug('Finished waiting for filterwheels.')

    def autofocus(self, *args, **kwargs):
        """ Autofocus the cameras.
        Args:
            *args, **kwargs: Parsed to camera.autofocus.
        Returns:
            dict: Dict of cam_name: threading.Event pairs.
        """
        cameras = {n: c for n, c in self.cameras.items() if c.has_focuser}

        # need to remove `filter_name` from kwargs so it only gets passed once
        # to `cameras[cam_name].autofocus()`
        filter_name = kwargs.pop('filter_name')

        def func(cam_name, filter_name=None, **kwargs):
            filter_name = self._get_focus_filter_name(cam_name, filter_name=filter_name, **kwargs)
            return cameras[cam_name].autofocus(filter_name=filter_name, **kwargs)

        return dispatch_parallel(func, cameras.keys(), filter_name=filter_name, **kwargs)

    # Private methods

    def _get_focus_filter_name(self, camera_name, filter_name=None, coarse=False, *args, **kwargs):
        """
        """
        if coarse or filter_name is None:
            return self.get_config('focusing.coarse.filter_name')
        elif isinstance(filter_name, abc.Mapping):
            try:
                return filter_name[camera_name]
            except KeyError as err:
                self.logger.warning(
                    f"No filter_name specified for camera {camera_name}, \
                    defaulting to coarse filter: {err!r}")
                return self.get_config('focusing.coarse.filter_name')
        else:
            return filter_name
