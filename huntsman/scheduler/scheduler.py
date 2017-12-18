from astropy import units as u

from pocs.scheduler import scheduler
from pocs.scheduler.field import Field

from pocs.scheduler.observation import Observation
from huntsman.scheduler.observation import DitheredObservation


class HunstmanBaseScheduler(scheduler.BaseScheduler):

    def add_observation(self, field_config):
        """Adds an `Observation` to the scheduler
        Args:
            field_config (dict): Configuration items for `Observation`
        """
        assert field_config['name'] not in self._observations.keys(), \
            self.logger.error("Cannot add duplicate field name")

        if 'exp_time' in field_config:
            field_config['exp_time'] = float(field_config['exp_time']) * u.second

        field = Field(field_config['name'], field_config['position'])

        try:
            if 'hdr_mode' in field_config:
                obs = DitheredObservation(field, **field_config)
            else:
                obs = Observation(field, **field_config)
        except Exception as e:
            self.logger.warning("Skipping invalid field config: {}".format(field_config))
            self.logger.warning(e)
        else:
            self._observations[field.name] = obs
