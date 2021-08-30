from panoptes.utils.error import PanError


class NotTwilightError(PanError):

    """ Error for when taking twilight flats and not twilight. """

    def __init__(self, msg='Not twilight', **kwargs):
        super().__init__(msg, **kwargs)
