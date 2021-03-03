from panoptes.pocs.scheduler.constraint import MoonAvoidance


class MoonAvoidance(MoonAvoidance):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_score(self, time, observer, observation, **kwargs):
        min_moon_sep = self.get_config('scheduler.constraints.min_moon_sep')
        super().get_score(time, observer, observation, min_moon_sep=min_moon_sep)
