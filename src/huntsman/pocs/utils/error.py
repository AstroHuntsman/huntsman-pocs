from panoptes.utils.error import *


class PyroError(PanError):
    """ Errors with the Pyro nameserver """

    def __init__(self, msg='Error with Pyro.', **kwargs):
        super().__init__(msg, **kwargs)


class PyroNameServerNotFound(PyroError):
    """ Errors with the Pyro nameserver """

    def __init__(self, msg='The Pyro nameserver could not be located.', **kwargs):
        super().__init__(msg, **kwargs)


class PyroProxyError(PyroError):
    """ Errors with the Pyro nameserver """

    def __init__(self, msg='The Pyro proxy could not be created.', **kwargs):
        super().__init__(msg, **kwargs)
