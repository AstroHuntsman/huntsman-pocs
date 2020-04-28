"""Import this module to register the required custom (de)serializers with Pyro.

This needs to be done for the server and the client. Currently custom serializers
included for astropy Quantities and the custom exceptions from POCS (pocs.utils.error).
"""
import re
import sys

import Pyro4
from Pyro4.util import SerializerBase
from astropy import units as u
from astropy.io.misc import yaml as ayaml

from panoptes.utils import error

# Enable local display of remote tracebacks
sys.excepthook = Pyro4.util.excepthook

# serializers/deserializers
error_pattern = re.compile(r"error\.(\w+)'>$")


def panerror_to_dict(obj):
    """Serialiser function for POCS custom exceptions."""
    name_match = error_pattern.search(str(obj.__class__))
    if name_match:
        exception_name = name_match.group(1)
    else:
        msg = f"Unexpected obj type: {obj}, {obj.__class__}"
        raise ValueError(msg)

    return {"__class__": "PanError",
            "exception_name": exception_name,
            "args": obj.args}


def dict_to_panerror(class_name, d):
    """Deserialiser function for POCS custom exceptions."""
    try:
        exception_class = getattr(error, d['exception_name'])
    except AttributeError:
        msg = f"error module has no exception class {d['exception_name']}."
        raise AttributeError(msg)

    return exception_class(*d["args"])


def astropy_to_dict(obj):
    """Serializer function for Astropy objects using astropy.io.misc.yaml.dump()."""
    return {"__class__": "astropy_yaml",
            "yaml_dump": ayaml.dump(obj)}


def dict_to_astropy(class_name, d):
    """De-serialiser function for Astropy objects using astropy.io.misc.yaml.load()."""
    return ayaml.load(d["yaml_dump"])


def value_error_to_dict(obj):
    """Serialiser function for ValueError."""
    return {"__class__": "ValueError",
            "args": [str(arg) for arg in obj.args]}


def dict_to_value_error(class_name, d):
    """De-serialiser function for ValueError."""
    return ValueError(*d["args"])


SerializerBase.register_class_to_dict(u.Quantity, astropy_to_dict)
SerializerBase.register_dict_to_class("astropy_yaml", dict_to_astropy)

SerializerBase.register_class_to_dict(error.PanError, panerror_to_dict)
SerializerBase.register_dict_to_class("PanError", dict_to_panerror)

# These two are only here as a temporary workaround for some typos in POCS
SerializerBase.register_class_to_dict(ValueError, value_error_to_dict)
SerializerBase.register_dict_to_class("ValueError", dict_to_value_error)
