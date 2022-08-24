"""
"""
import yaml
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pytz import timezone

from panoptes.utils.library import load_module
from panoptes.utils.time import current_time, wait_for_events
from panoptes.utils.utils import altaz_to_radec

from huntsman.pocs.utils.huntsman import create_huntsman_pocs
from huntsman.pocs.observatory import HuntsmanObservatory

SLEEP_INTERVAL = 60
FOCUS_TIMEOUT = 900
TIMEZONE = timezone('Australia/Sydney')
DATE_BEGIN = datetime(2021, 6, 7, tzinfo=TIMEZONE)  # Change as needed
FIELDS_FILE = "/huntsman/conf_files/fields.yaml"

FILTER_NAMES = {"huntsmanpi005": "g_band",
                "huntsmanpi007": "g_band",
                "huntsmanpi008": "r_band",
                "huntsmanpi009": "r_band",
                "huntsmanpi011": "r_band"}


TEST_OBSERVATION_CONFIGS = [{"observation":
                            {"name": "spica",
                             "type": "huntsman.pocs.scheduler.observation.base.Observation"},
                             "field": {"name": "spica",
                                       "type": "huntsman.pocs.scheduler.field.Field",
                                       "position": "13h26m20s -11d16m21s"},
                             "time_start": "16:05:00",
                             "time_end": "18:25:00"}
                            ]


class DwfScheduler():
    """ Class to return valid observations based on local time. """

    def __init__(self, observations, times_start, times_end):
        self._observations = observations
        self._times_start = times_start
        self._times_end = times_end

    def get_observation(self):
        """ Get an observation to observe now! """
        time_now = datetime.now(TIMEZONE).replace(tzinfo=TIMEZONE)

        valid_obs = None
        for i in range(len(self._observations)):

            obs = self._observations[i]

            if (time_now > self._times_start[i]) and (time_now < self._times_end[i]):
                valid_obs = obs
                break

        if valid_obs:
            # Remove the observation so we don't accidentally observe it again
            del self._observations[i]
            del self._times_start[i]
            del self._times_end[i]

        return valid_obs


def parse_date(date):
    """ Parse the date from the fields config file. """

    hour, minute, sec = [int(_) for _ in date.split(":")]

    td = timedelta(hours=hour, minutes=minute, seconds=sec)
    if hour < 12:
        td += timedelta(days=1)

    return DATE_BEGIN + td


def create_scheduler(observation_configs=None):
    """ Create the DWF scheduler object. """

    observations = []
    times_start = []
    times_end = []

    if observation_configs is None:
        with open(FIELDS_FILE, 'r') as f:
            observation_configs = yaml.safe_load(f)
    else:
        observation_configs = deepcopy(observation_configs)

    for config in observation_configs:

        time_start = parse_date(config.pop("time_start"))
        time_end = parse_date(config.pop("time_end"))

        times_start.append(time_start)
        times_end.append(time_end)

        field_config = config["field"]
        FieldClass = load_module(field_config.pop("type"))
        field = FieldClass(**field_config)

        obs_config = config["observation"]
        ObsClass = load_module(obs_config.pop("type"))
        obs = ObsClass(filter_names_per_camera=FILTER_NAMES, field=field, **obs_config)
        observations.append(obs)

    scheduler = DwfScheduler(observations=observations, times_start=times_start,
                             times_end=times_end)

    return scheduler


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


if __name__ == "__main__":

    huntsman = create_huntsman_pocs(with_dome=True, simulators=["weather", "power", "night"])
    scheduler = create_scheduler()

    # Open the dome
    huntsman.observatory.dome.open()

    # Prepare the cameras
    huntsman.observatory.prepare_cameras()

    # Move FWs to their separate positions
    for cam_name, filter_name in FILTER_NAMES.items():
        huntsman.observatory.cameras[cam_name].filterwheel.move_to(filter_name, blocking=True)

    # Slew to focus
    huntsman.observatory.mount.unpark()
    huntsman.observatory.mount.set_target_coordinates(get_focus_coords(huntsman))
    huntsman.observatory.mount.slew_to_target()

    # Do coarse focus
    # Use super method to override filter wheel move
    events = super(HuntsmanObservatory, huntsman.observatory).autofocus_cameras(coarse=True)
    wait_for_events(list(events.values()), timeout=FOCUS_TIMEOUT)

    # Do fine focus
    # We may have to do this several times per night, so monitor the FITS images as they come in
    events = super(HuntsmanObservatory, huntsman.observatory).autofocus_cameras()
    wait_for_events(list(events.values()), timeout=FOCUS_TIMEOUT)

    # Start the observation loop
    while True:

        observation = scheduler.get_observation()

        if observation is None:
            huntsman.logger.debug(f"No valid observation. Sleeping for {SLEEP_INTERVAL}s.")
            time.sleep(SLEEP_INTERVAL)
            continue

        huntsman.logger.info(f"Taking observation: {observation}")
        huntsman.observatory.take_observation_block(observation, skip_focus=True)
