from panoptes.utils.error import *


class PyroNameServerNotFound(PanError):
    """ Errors with the Pyro nameserver """

    def __init__(self, msg='The Pyro nameserver could not be located.', **kwargs):
        super().__init__(msg, **kwargs)
