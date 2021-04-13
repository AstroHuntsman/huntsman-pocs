from huntsman.pocs.scheduler.observation.base import AbstractObservation
from huntsman.pocs.scheduler.observation.dithered import DitheredObservation
from huntsman.pocs.scheduler.field import OffsetSkyField


class OffsetSkyObservation(AbstractObservation):
    """ Observation with paired offset sky field. Successive exposures will switch between the
    target and sky coordianates."""

    def __init__(self, field, observation_type=DitheredObservation,
                 observation_kwargs=None, batch_size=3, **kwargs):
        """
        Args:
        """
        if not isinstance(field, OffsetSkyField):
            raise ValueError("field must be an instance of OffsetSkyField.")

        super().__init__(**kwargs)

        self._field = field
        self.batch_size = int(batch_size)

        if observation_kwargs is None:
            observation_kwargs = {}

        self.target_observation = observation_type(field=self._field.target_field,
                                                   **observation_kwargs)
        self.sky_observation = observation_type(field=self._field.sky_field,
                                                **observation_kwargs)

    # Properties

    @property
    def on_target(self):
        """ Return True if current exposure is on-target, else False (on-sky). """
        return (self.exposure_num / self.batch_size) % 2 == 0

    @property
    def field(self):
        if self.on_target:
            return self._field.target_field
        return self._field.sky_field

    @field.setter
    def field(self, field):
        raise NotImplementedError

    @property
    def exposure_index(self):
        return self.target_observation.exposure_idx + self.sky_observation.exposure_idx

    @property
    def set_is_finished(self):
        return self.target_observation.set_is_finished and self.sky_observation.set_is_finished

    # Methods

    def reset(self):
        self.target_observation.reset()
        self.sky_observation.reset()
