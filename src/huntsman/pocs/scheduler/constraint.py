from panoptes.pocs.scheduler.constraint import MoonAvoidance


class MoonAvoidance(MoonAvoidance):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_score(self, *args, **kwargs):
        min_moon_sep = self.get_config('scheduler.constraints.min_moon_sep')
        return super().get_score(min_moon_sep=min_moon_sep, *args, **kwargs)
