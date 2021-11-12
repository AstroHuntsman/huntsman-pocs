import os
import threading
import time
from contextlib import suppress
from panoptes.utils.time import current_time
from panoptes.utils import error
from panoptes.pocs.camera.camera import AbstractCamera

from huntsman.pocs.camera.utils import tune_exposure_time


class AbstractHuntsmanCamera(AbstractCamera):

    def take_observation(self, observation, headers=None, filename=None, blocking=False, **kwargs):
        """Take an observation. Override of `panoptes.pocs.camera.camera.take_observation()` to
        allow multifilter observations and dynamic exposure time tuning.

        Gathers various header information, sets the file path, and calls
            `take_exposure`. Also creates a `threading.Event` object and a
            `threading.Thread` object. The Thread calls `process_exposure`
            after the exposure had completed and the Event is set once
            `process_exposure` finishes.
        Args:
            observation (~panoptes.pocs.scheduler.observation.Observation): Object
                describing the observation
            headers (dict, optional): Header data to be saved along with the file.
            filename (str, optional): pass a filename for the output FITS file to
                override the default file naming system.
            blocking (bool): If method should wait for observation event to be complete
                before returning, default False.
            **kwargs (dict): Optional keyword arguments (`exptime`, dark)
        Returns:
            threading.Event: An event to be set when the image is done processing
        """
        observation_event = threading.Event()
        # Setup the observation
        exptime, file_path, image_id, metadata = self._setup_observation(observation,
                                                                         headers,
                                                                         filename,
                                                                         **kwargs)

        # Get camera-specific filter name
        with suppress(AttributeError):
            filter_name = observation.get_filter_name(self.name)

        # pop exptime from kwarg as its now in exptime
        exptime = kwargs.pop('exptime', observation.exptime.value)

        # Move the filterwheel now so we can tune the exptime properly
        if self.has_filterwheel:
            if filter_name is not None:
                self.filterwheel.move_to(filter_name)
            else:
                self.logger.warning(f"No filter name specified for {observation}")
                try:
                    self.filterwheel.move_to_light_position()
                except error.NotFound as err:
                    self.logger.warning(f"{err!r}")

        # pop exptime from kwarg as its now in exptime
        exptime = kwargs.pop('exptime', observation.exptime.value)

        # Check if we need to tune the exposure time
        with suppress(AttributeError):
            if observation.target_exposure_scaling is not None:
                exptime = tune_exposure_time(target=observation.target_exposure_scaling,
                                             initial_exptime=observation.exptime,
                                             **observation.tune_exptime_kwargs)

        # start the exposure
        self.take_exposure(seconds=exptime, filename=file_path, blocking=blocking,
                           dark=observation.dark, **kwargs)

        # Add most recent exposure to list
        if self.is_primary:
            if 'POINTING' in metadata:
                observation.pointing_images[image_id] = file_path
            else:
                observation.exposure_list[image_id] = file_path

        # Process the exposure once readout is complete
        # To be used for marking when exposure is complete (see `process_exposure`)
        t = threading.Thread(
            name=f'Thread-{image_id}',
            target=self.process_exposure,
            args=(metadata, observation_event),
            daemon=True)
        t.start()

        if blocking:
            while not observation_event.is_set():
                self.logger.trace('Waiting for observation event')
                time.sleep(0.5)

        return observation_event

    def _setup_observation(self, observation, headers, filename, **kwargs):
        """Override of `panoptes.pocs.camera.camera._setup_observation()`  to use the
        `observation.get_filter_name()` method to set observation `filter_name`, rather than
        checking the `observation.filter_name` attribute directly. This enables multi
        filter observations.

        Args:
            observation (~panoptes.pocs.scheduler.observation.Observation): Object
                describing the observation
            headers (dict, optional): Header data to be saved along with the file.
            filename (str, optional): pass a filename for the output FITS file to
                override the default file naming system.

        """
        headers = headers or None

        # Get filtername for observation
        filter_name = observation.get_filter_name(self.name)

        # Move the filterwheel if necessary
        if self.has_filterwheel:
            if filter_name is not None:
                try:
                    # Move the filterwheel
                    self.logger.debug(
                        f'Moving filterwheel={self.filterwheel} to filter_name='
                        f'{filter_name}')
                    self.filterwheel.move_to(filter_name, blocking=True)
                except Exception as e:
                    self.logger.error(f'Error moving filterwheel on {self} to'
                                      f' {observation.filter_name}: {e!r}')
                    raise (e)

            elif not observation.dark:
                self.logger.warning(f'Filter {observation.filter_name} requested by'
                                    f' observation but {self.filterwheel} is missing that filter, '
                                    f'using {self.filter_type}.')

        if headers is None:
            start_time = current_time(flatten=True)
        else:
            start_time = headers.get('start_time', current_time(flatten=True))

        if not observation.seq_time:
            self.logger.debug(f'Setting observation seq_time={start_time}')
            observation.seq_time = start_time

        # Get the filename
        self.logger.debug(
            f'Setting image_dir={observation.directory}/{self.uid}/{observation.seq_time}')
        image_dir = os.path.join(
            observation.directory,
            self.uid,
            observation.seq_time
        )

        # Get full file path
        if filename is None:
            file_path = os.path.join(image_dir, f'{start_time}.{self.file_extension}')
        else:
            # Add extension
            if '.' not in filename:
                filename = f'{filename}.{self.file_extension}'

            # Add directory
            if '/' not in filename:
                filename = os.path.join(image_dir, filename)

            file_path = filename

        self.logger.debug(f'Setting file_path={file_path}')

        unit_id = self.get_config('pan_id')

        # Make the IDs.
        sequence_id = f'{unit_id}_{self.uid}_{observation.seq_time}'
        image_id = f'{unit_id}_{self.uid}_{start_time}'

        self.logger.debug(f"sequence_id={sequence_id} image_id={image_id}")

        # The exptime header data is set as part of observation but can
        # be overridden by passed parameter so update here.
        exptime = kwargs.get('exptime', observation.exptime.value)

        # Camera metadata
        metadata = {
            'camera_name': self.name,
            'camera_uid': self.uid,
            'field_name': observation.field.field_name,
            'file_path': file_path,
            'filter': self.filter_type,
            'image_id': image_id,
            'is_primary': self.is_primary,
            'sequence_id': sequence_id,
            'start_time': start_time,
            'exptime': exptime
        }
        if filter_name is not None:
            metadata['filter_request'] = filter_name

        if headers is not None:
            self.logger.trace(f'Updating {file_path} metadata with provided headers')
            metadata.update(headers)

        self.logger.debug(
            f'Observation setup: exptime={exptime!r} file_path={file_path!r} '
            f'image_id={image_id!r} metadata={metadata!r}')

        return exptime, file_path, image_id, metadata
