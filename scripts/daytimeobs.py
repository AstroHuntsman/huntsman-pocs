"""
Script for observing something during the day.
- Open / close dome.
- Slew to target.
- Focus cameras.
- Take observations.
- Verify safety at each step (solar distance, weather etc).

NOTE: This script will be superceeded by scheduler when we can impose arbitrary horizon ranges
for a given target.
"""
import argparse

from astropy import units as u

from panoptes.utils.time import current_time
from huntsman.pocs.utils.huntsman import create_huntsman_scheduler, create_huntsman_pocs

SLEEP_INTERVAL = 30  # Sleep this long in seconds between safety checks before starting up


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("field_name", type=str,
                        help="The name of the field to observe. If more than one match in the"
                             " fields file, they will be observed in turn according to their"
                             " priority.")
    parser.add_argument("--simulate_weather", action="store_true",
                        help="If provided, will run POCS with weather simulator.")
    parser.add_argument("--no_dome", action="store_true",
                        help="If provided, will run POCS with the dome closed e.g. for testing.")

    # Parse command line input
    args = parser.parse_args()
    field_name = args.field_name
    use_weather_simulator = args.simulate_weather
    with_dome = not args.no_dome
    with_autoguider = False

    # Create scheduler and override targets list
    scheduler = create_huntsman_scheduler()
    scheduler._observations = {k: v for k, v in scheduler._observations.items() if k == field_name}
    if not scheduler._observations:
        raise ValueError(f"No observations matching '{field_name}' in targets file.")

    # Note we use "night" simulator so we can observe in the day
    # Weather simulator is optional because weather reading currently unreliable
    simulators = ["night", "power"]
    if use_weather_simulator:
        simulators.append("weather")

    # Create HuntsmanPOCS instance
    huntsman = create_huntsman_pocs(simulators=simulators, scheduler=scheduler, with_dome=with_dome,
                                    with_autoguider=with_autoguider)

    # NOTE: Avoid coarse focusing state because it slews to a fixed position on-sky
    # This position may be too close to the Sun and it is unlikely there will be any stars
    huntsman.observatory.last_coarse_focus_time = current_time()
    huntsman.observatory.last_coarse_focus_temp = huntsman.observatory.temperature
    huntsman.observatory._coarse_focus_temptol = 100 * u.Celsius
    huntsman.observatory._coarse_focus_interval = 100 * u.hour

    # Select the observation and use it to configure focusing exposure times
    # TODO: Do this automatically
    obs_name = scheduler.get_observation()[0]
    observation = scheduler.observations[obs_name]

    # Override the fine focus settings to make it mimic coarse focus
    # TODO: Set this automatically based on time of day and alt / az?
    for camera in huntsman.observatory.cameras.values():

        autofocus_range = list(camera._proxy.get("autofocus_range", "focuser"))
        autofocus_range[0] = autofocus_range[1]
        camera._proxy.set("autofocus_range", autofocus_range, "focuser")

        autofocus_step = list(camera._proxy.get("autofocus_step", "focuser"))
        autofocus_step[0] = autofocus_step[1]
        camera._proxy.set("autofocus_step", autofocus_step, "focuser")

        # Also override the focusing exposure time
        # TODO: Set this automatically based on time of day and alt / az
        camera._proxy.set("autofocus_seconds", observation.exptime, "focuser")

    # Run the state machine
    # NOTE: We don't have to bypass darks, flats etc because using night simulator
    # NOTE: Bypass initial coarse focus in favour of coarser fine focus
    huntsman.run(initial_focus=False)
