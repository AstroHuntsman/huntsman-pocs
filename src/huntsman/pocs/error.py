from panoptes.utils.error import PanError


class NotTwilightError(PanError):

    """ Error for when taking twilight flats and not twilight. """

    def __init__(self, msg='Not twilight', **kwargs):
        super().__init__(msg, **kwargs)


class NoDarksDuringTwilightError(PanError):
    """ Error for when attempt to take darks during twilight. """

    def __init__(self, msg="Don't take darks during twilight", **kwargs):
        super().__init__(msg, **kwargs)


class NotSafeError(PanError):

    """ Error for when safety fails. """

    def __init__(self, msg='Not safe', **kwargs):
        super().__init__(msg, **kwargs)
