from astropy import units as u

from pocs.scheduler import dispatch
from pocs.scheduler.field import Field
from pocs.utils import current_time
from pocs.scheduler.observation import Observation

from huntsman.scheduler.observation import DitheredObservation
from huntsman.utils import dither


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
                self.logger.info(field_config)
                obs = DitheredObservation(field, **field_config)

                obs.seq_time = current_time(flatten=True)

                dither_pattern_offset = 5 * u.arcmin
                dither_random_offset = 0.5 * u.arcmin
                n_positions = 9

                dither_coords = dither.get_dither_positions(obs.field.coord,
                                                            n_positions=n_positions,
                                                            pattern=dither.dice9,
                                                            pattern_offset=dither_pattern_offset,
                                                            random_offset=dither_random_offset)

                self.logger.debug(
                    "Dither Coords for Flat-field: {}".format(dither_coords))

                fields = [Field(field_config['name'], coord)
                          for i, coord in enumerate(dither_coords)]
                exptimes = [obs.exptime for coord in dither_coords]

                obs.field = fields
                obs.exptime = exptimes
                obs.min_nexp = len(fields)
                obs.exp_set_size = len(fields)

            else:
                obs = Observation(field, **field_config)
        except Exception as e:
            self.logger.warning(
                "Skipping invalid field config: {}".format(field_config))
            self.logger.warning(e)
        else:
            self._observations[field.name] = obs
