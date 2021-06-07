"""
"""
import time
from datetime import datetime

from panoptes.utils.time import current_time
from panoptes.utils.utils import altaz_to_radec

from huntsman.pocs.scheduler.observation.base import Observation
from huntsman.pocs.utils.huntsman import create_huntsman_pocs

SLEEP_INTERVAL = 10

FILTER_NAMES = {"huntsmanpi005": "g_band",
                "huntsmanpi007": "g_band",
                "huntsmanpi008": "r_band",
                "huntsmanpi009": "r_band",
                "huntsmanpi011": "r_band"}

OBSERVATION_CONFIG = []


def get_focus_coords(huntsman):
    """ Get coordinates for initial focus. """
    coarse_focus_config = huntsman.get_config('focusing.coarse')

    # Get timeout, alt, and az from config dict.
    coarse_focus_alt = coarse_focus_config['alt']
    coarse_focus_az = coarse_focus_config['az']

    # Convert altaz coordinates to radec.
    coarse_focus_coords = altaz_to_radec(alt=coarse_focus_alt, az=coarse_focus_az,
                                         location=huntsman.observatory.earth_location,
                                         obstime=current_time())

    return coarse_focus_coords


class DwfScheduler():
    """ Hardcode the field configs here for simplicity. """

    def __init__(self, observations, times_start, times_end):
        self._observations = observations
        self._times_start = times_start
        self._times_end = times_end

    def get_observation(self):
        """ Get an observation to observe now! """
        time_now = datetime.now()

        valid_obs = None
        for i in range(len(self._observations)):

            obs = self._observations[i]

            if (time_now > self._times_start[i]) and (time_now < self._times_end[i]):
                valid_obs = obs

        if valid_obs:
            # Remove the observation so we don't accidentally observe it again
            del self._observations[i]

        return valid_obs


if __name__ == "__main__":

    huntsman = create_huntsman_pocs()

    observations = []
    times_start = []
    times_end = []
    for obs_config in OBSERVATION_CONFIG:
        times_start.append(obs_config.pop("time_start"))
        times_end.append(obs_config.pop("time_end"))
        observations.append(Observation(filter_names_per_camera=FILTER_NAMES, **obs_config))

    scheduler = DwfScheduler(observations=observations, times_start=times_start,
                             times_end=times_end)

    # Open the dome
    huntsman.observatory.dome.open()

    # Prepare the cameras
    huntsman.observatory.prepare_cameras()

    # Move FWs to their separate positions
    for cam_name, filter_name in FILTER_NAMES.items():
        huntsman.cameras[cam_name].filterwheel.move_to(filter_name, blocking=True)

    # Slew to focus
    huntsman.observatory.mount.set_target_coordinates(get_focus_coords(huntsman))
    huntsman.observatory.mount.slew_to_target()

    # Do coarse focus
    # Use a bad filter name (not None) to make the code use the current filter in each camera
    huntsman.observatory.autofocus_cameras(filter_name="notafiltername", coarse=True)

    # Do fine focus
    # We may have to do this several times per night, so monitor the FITS images as they come in
    huntsman.observatory.autofocus_cameras(filter_name="notafiltername")

    # Start the observation loop
    while True:

        observation = scheduler.get_observation()

        if observation is None:
            huntsman.logger.debug(f"No valid observation. Sleeping for {SLEEP_INTERVAL}s.")
            time.sleep(SLEEP_INTERVAL)
            continue

        huntsman.logger.info(f"Taking observation: {observation}")
        huntsman.observatory.take_observation_block(observation, skip_focus=True)
