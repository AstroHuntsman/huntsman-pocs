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


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("field_name", type=str,
                        help="The name of the field to observe. If more than one match in the"
                             " fields file, they will be observed in turn according to their"
                             " priority.")
    parser.add_argument("--simulate_weather", action="store_true",
                        help="If provided, will run POCS with weather simulator.")

    # Parse command line input
    args = parser.parse_args()
    field_name = args.field_name
    use_weather_simulator = args.simulate_weather

    # Create scheduler and override targets list
    # This is a hack
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
    huntsman = create_huntsman_pocs(simulators=simulators, scheduler=scheduler)

    # NOTE: Avoid coarse focusing state because it slews to a fixed position on-sky
    # This position may be too close to the Sun and it is unlikely there will be any stars
    # This is a hack
    huntsman.observatory.last_coarse_focus_time = current_time()
    huntsman.observatory.last_coarse_focus_temp = huntsman.observatory.temperature
    huntsman.observatory._coarse_focus_temptol = 100 * u.Celsius
    huntsman.observatory._coarse_focus_interval = 100 * u.hour

    # Do a coarse focus at a convenient and safe position, e.g. first observation
    obs_name = scheduler.get_observation()[0]
    observation = scheduler.observations[obs_name]
    huntsman.observatory.slew_to_observation(observation)
    huntsman.observatory.autofocus_cameras(coarse=True, filter_name=observation.filter_name)

    # Run the state machine
    # NOTE: We don't have to bypass darks, flats etc because using night simulator
    huntsman.run(initial_focus=False)
