from astropy import units as u

from panoptes.utils.utils import get_quantity_value
from panoptes.pocs.scheduler.constraint import BaseConstraint, MoonAvoidance
from huntsman.pocs.utils.safety import check_solar_separation_safety


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
                                         time=time, min_separation=self.min_separation, **kwargs):
            score = 1
        else:
            veto = True

        return veto, score * self.weight

    def __str__(self):
        return "Sun Avoidance"
