from panoptes.utils import current_time
from panoptes.utils import wait_for_events


def take_pics(field,
              observation,
              cameras,
              base_date=None,
              num_exposures=1,
              base_dir='/var/huntsman/images/temp'
              take_flats=False):
    """Takes pics with the cameras"""

    # Set a base date for all pics and use that as directory name.
    base_date = base_date or current_time(flatten=True)

    for i in range(num_exposures):
        print(f"Starting exposures {i:03d} of {num_exposures:03d}.")

        exposure_events = []

        # Share timestamp filename across all cameras.
        timestamp = current_time(flatten=True)
        for cam_name, camera in cameras.items():
            new_filename = f'{base_dir}/{base_date}/{camera.uid}/{timestamp}.fits'

            exposure_events.append(camera.take_observation(observation, filename=new_filename))
            print(f"Exposure {new_filename} started.")

        print(f"Waiting for exposures {i:03d}/{num_exposures:03d}")
        wait_for_events(exposure_events)


if __name__ == '__main__':

    test_exptime = 0.07 * u.second
    test_coordinates = SkyCoord('00h00m00s', '+00d00m00s', frame='icrs')
    test_field = Field(name='day_flats', position=test_coordinates)
    test_observation = Observation(field=test_field, exptime=test_exptime, min_nexp=1,
                               exp_set_size=1, priority=100, filter_name='halpha')


    take_pics(field=test_field,
              observation=test_observation,
              cameras=create_cameras_from_config(), # or single camera if needed
              base_date=None,
              exptime=test_exptime,
              num_exposures=1,
              base_dir='/var/huntsman/images/temp/dayflats/')
