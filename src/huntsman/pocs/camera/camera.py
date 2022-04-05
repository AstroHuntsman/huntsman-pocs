import os
import threading
import time
from contextlib import suppress
from panoptes.utils.time import current_time
from panoptes.pocs.camera.camera import AbstractCamera

from panoptes.utils.utils import get_quantity_value
import tempfile
import numpy as np
from astropy import units as u


class AbstractHuntsmanCamera(AbstractCamera):
    """Base class for Huntsman cameras"""

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
            headers (dict or Header, optional): Header data to be saved along with the file.
            filename (str, optional): pass a filename for the output FITS file to
                override the default file naming system.
            blocking (bool): If method should wait for observation event to be complete
                before returning, default False.
            **kwargs (dict): Optional keyword arguments (`exptime`, dark)

        Returns:
            dict: The metadata from the event.
        """
        # Set the camera is_observing.
        self._is_observing_event.set()

        # Setup the observation
        metadata = self._setup_observation(observation, headers, filename, **kwargs)
        exptime = metadata['exptime']
        file_path = metadata['filepath']
        image_id = metadata['image_id']

        # pop exptime from kwarg as its now in exptime
        exptime = kwargs.pop('exptime', observation.exptime.value)

        # Check if we need to tune the exposure time
        # (should this go in setup_observation?)
        with suppress(AttributeError):
            if observation.target_exposure_scaling is not None:
                exptime = self.tune_exposure_time(target=observation.target_exposure_scaling,
                                                  initial_exptime=observation.exptime,
                                                  **observation.tune_exptime_kwargs)

        # start the exposure
        self.take_exposure(seconds=exptime, filename=file_path, blocking=blocking,
                           metadata=metadata, dark=observation.dark, **kwargs)

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
            args=(metadata,),
            daemon=True)
        t.start()

        if blocking:
            while self.is_observing:
                self.logger.trace('Waiting for observation event')
                time.sleep(0.1)

        return metadata

    def tune_exposure_time(self, target, initial_exptime, min_exptime=0, max_exptime=None,
                           max_steps=5, tolerance=0.1, cutout_size=256, bias=None, **kwargs):
        """ Tune the exposure time to within certain tolerance of the desired counts.
        TODO: Add as camera method.
        """
        self.logger.info(f"Tuning exposure time for {self}.")

        images_dir = self.get_config("directories.images", None)
        if images_dir:
            images_dir = os.path.join(images_dir, "temp")
            os.makedirs(images_dir, exist_ok=True)

        # Parse quantities
        initial_exptime = get_quantity_value(initial_exptime, "second") * u.second

        if min_exptime is not None:
            min_exptime = get_quantity_value(min_exptime, "second") * u.second
        if max_exptime is not None:
            max_exptime = get_quantity_value(max_exptime, "second") * u.second

        try:
            bit_depth = self.bit_depth.to_value("bit")
        except NotImplementedError:
            bit_depth = 16

        saturated_counts = 2 ** bit_depth

        prefix = images_dir if images_dir is None else images_dir + "/"
        with tempfile.NamedTemporaryFile(suffix=".fits", prefix=prefix, delete=False) as tf:

            exptime = initial_exptime

            for step in range(max_steps):

                # Check if exposure time is within valid range
                if (exptime == max_exptime) or (exptime == min_exptime):
                    break

                # Get an image
                cutout = self.get_cutout(exptime, tf.name, cutout_size, keep_file=False, **kwargs)
                cutout = cutout.astype("float32")
                if bias is not None:
                    cutout -= bias

                # Measure average counts
                normalised_counts = np.median(cutout) / saturated_counts

                self.logger.debug(f"Normalised counts for {exptime} exposure on {self}:"
                                  f" {normalised_counts}")

                # Check if tolerance condition is met
                if tolerance:
                    if abs(normalised_counts - target) < tolerance:
                        break

                # Update exposure time
                exptime = exptime * target / normalised_counts
                if max_exptime is not None:
                    exptime = min(exptime, max_exptime)
                if min_exptime is not None:
                    exptime = max(exptime, min_exptime)

        self.logger.info(f"Tuned exposure time for {self}: {exptime}")

        return exptime

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
                                      f' {filter_name}: {e!r}')
                    raise (e)

            elif not observation.dark:
                self.logger.warning(f'Filter {filter_name} requested by'
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
        exptime = kwargs.get('exptime', get_quantity_value(observation.exptime, unit=u.second))

        # Camera metadata
        metadata = {
            'camera_name': self.name,
            'camera_uid': self.uid,
            'field_name': observation.field.field_name,
            'filepath': file_path,
            'filter': self.filter_type,
            'image_id': image_id,
            'is_primary': self.is_primary,
            'sequence_id': sequence_id,
            'start_time': start_time,
            'exptime': exptime,
            'current_exp_num': observation.current_exp_num
        }
        if filter_name is not None:
            metadata['filter_request'] = filter_name

        metadata.update(observation.status)

        if headers is not None:
            self.logger.trace(f'Updating {file_path} metadata with provided headers')
            metadata.update(headers)

        self.logger.debug(
            f'Observation setup: exptime={exptime!r} file_path={file_path!r} '
            f'image_id={image_id!r} metadata={metadata!r}')

        return metadata
