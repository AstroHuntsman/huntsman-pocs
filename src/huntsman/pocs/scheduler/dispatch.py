from astropy import units as u

from panoptes.utils.time import current_time

from panoptes.pocs.scheduler import dispatch
from panoptes.pocs.scheduler.field import Field
from huntsman.pocs.scheduler.observation.base import Observation

from huntsman.pocs.scheduler.observation.dithered import DitheredObservation


class Scheduler(dispatch.Scheduler):

    def add_observation(self, field_config):
        """Adds an `Observation` to the scheduler
        Args:
            field_config (dict): Configuration items for `Observation`
        """
        assert field_config['name'] not in self._observations.keys(), \
            self.logger.error("Cannot add duplicate field name")

        if 'exptime' in field_config:
            field_config['exptime'] = float(
                field_config['exptime']) * u.second

        field = Field(field_config['name'], field_config['position'])

        try:
            self.logger.info("Creating observation")
            if 'no_dither' not in field_config:
                self.logger.info("Creating DitheredObservation")
                obs = DitheredObservation(field, **field_config)
                obs.seq_time = current_time(flatten=True)
            else:
                obs = Observation(field, **field_config)
        except Exception as e:
            self.logger.warning(
                "Skipping invalid field config: {}".format(field_config))
            self.logger.warning(e)
        else:
            self._observations[field.name] = obs
