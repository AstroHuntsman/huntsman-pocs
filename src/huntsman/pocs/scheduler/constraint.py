from contextlib import suppress

from astropy import units as u

from panoptes.utils.utils import get_quantity_value
from panoptes.pocs.scheduler.constraint import BaseConstraint, MoonAvoidance, Altitude
from huntsman.pocs.utils.safety import check_solar_separation_safety
from huntsman.pocs.scheduler.observation.base import CompoundObservation


class MoonAvoidance(MoonAvoidance):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_score(self, *args, **kwargs):
        min_moon_sep = self.get_config('scheduler.constraints.min_moon_sep')
        return super().get_score(min_moon_sep=min_moon_sep, *args, **kwargs)


class SunAvoidance(BaseConstraint):
    """ Sun avoidance constraint is similar to MoonAvoidance apart from a few differences:
    - Targets are not penalised for being close to the Sun if they are outside the min separation.
    - Safety is evaluated accross the whole exposure time rather than just the scheduling instant.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        min_sep = self.get_config("scheduler.constraints.sun_avoidance.min_separation", 10)
        self.min_separation = get_quantity_value(min_sep, u.deg) * u.deg

    def get_score(self, time, observer, observation, **kwargs):
        """ Veto the observation if too close to the Sun. """
        veto = False
        score = self._score

        if check_solar_separation_safety(observation=observation, location=observer.location,
                                         time=time, min_separation=self.min_separation):
            score = 1
        else:
            veto = True

        return veto, score * self.weight

    def __str__(self):
        return "Sun Avoidance"


class Altitude(Altitude):
    """ Implements altitude constraints for a horizon """

    def get_score(self, time, observer, observation, **kwargs):
        veto = False
        score = self._score

        # If the observation is a compoundobs we want to assess all the
        # fields, not just the first field
        if isinstance(observation, CompoundObservation):
            targets = observation._field
        else:
            # if not a compound obs, just create a list containing the single field of a regular obs
            targets = [observation.field]

        # Note we just get nearest integer
        target_azs = []
        target_alts = []
        for target in targets:
            target_azs.append(observer.altaz(time, target=target).az.degree)
            target_alts.append(observer.altaz(time, target=target).alt.degree)

        # Determine if the target altitude is above or below the determined
        # minimum elevation for that azimuth
        min_alts = [self.horizon_line(int(target_az)) for target_az in targets_az]

        vetos = []
        for min_alt, target_alt, target_az in zip(min_alts, target_alts, target_azs):
            with suppress(AttributeError):
                min_alt = get_quantity_value(min_alt, u.degree)
            self.logger.debug(f'Target coords: {target_az=:.02f} {target_alt=:.02f}')
            if target_alt < min_alt:
                self.logger.debug(f"Below minimum altitude: {target_alt:.02f} < {min_alt:.02f}")
                veto = True
                vetos.append(veto)
            else:
                score = 1

        # if any of the target fields are below min altitude then veto the observation
        veto = all(vetos)
        return veto, score * self.weight
