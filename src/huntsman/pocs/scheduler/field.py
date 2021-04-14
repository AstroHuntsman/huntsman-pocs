from astroplan import FixedTarget
from astropy.coordinates import SkyCoord

from panoptes.utils.library import load_module
from panoptes.pocs.base import PanBase
from huntsman.pocs.utils import dither


class AbstractField(PanBase):

    def __init__(self, name, equinox="J2000", frame="icrs", **kwargs):
        """ Abstract base class for Field objects.
        Args:
            name (str): The name of the field (e.g. target name).
            equinox (str, optional): The equinox, parsed to astropy.coordinates.SkyCoord.
                Default: J2000.
            frame (str, option): The frame to be parsed to astropy.coordinates.SkyCoord.
                Default: icrs.
            **kwargs: parsed to PanBase.__init__.
        """
        super().__init__(**kwargs)

        self.equinox = equinox
        self.frame = frame
        self.name = name

        # Prepare the field name
        self._field_name = self.name.title().replace(' ', '').replace('-', '')
        if not self._field_name:
            raise ValueError('Name is empty.')

    def __name__(self):
        return self.__class__.__name__

    def __str__(self):
        return f"{self.__name__}: {self.name}"

    # Properties

    @property
    def field_name(self):
        """ Flattened field name appropriate for paths. """
        return self._field_name


class Field(FixedTarget, AbstractField):

    def __init__(self, name, position, **kwargs):
        """ An object representing an area to be observed.
        A `Field` corresponds to an `~astroplan.ObservingBlock` and contains information
        about the center of the field (represented by an `astroplan.FixedTarget`).
        Args:
            name (str): The name of the field (e.g. target name).
            position (str or SkyCoord): The coordinates of the field centre.
            **kwargs: Parsed to AbstractField.__init__.
        """
        AbstractField.__init__(self, name=name, **kwargs)

        # Initialise the FixedTarget base class
        if isinstance(position, SkyCoord):
            coord = position
        else:
            coord = SkyCoord(position, equinox=self.equinox, frame=self.frame)
        super().__init__(coord, name=name)


class CompoundField(AbstractField):
    """ An iterable, indexable class consisting of several fields. """

    def __init__(self, name, field_config_list,
                 default_field_type="huntsman.pocs.scheduler.field.Field", **kwargs):
        """
        Args:
            name (str): The name of the field (e.g. target name).
            field_config_list (list of dict): Config for each field.
            default_field_type (str, optional): The default python class name to use for the
                sub-fields. This can be overridden by providing the 'type' item to the field_config.
                Default: huntsman.pocs.scheduler.field.Field.
        """
        super().__init__(name, **kwargs)

        self._idx = 0
        self._fields = []

        for field_config in field_config_list:

            field_type = field_config.pop("type", default_field_type)
            self.logger.debug(f"Adding {field_type} field to {name} observation.")
            field_class = load_module(field_type)

            self._fields.append(field_class(**field_config))

    def __getitem__(self, index):
        return self._fields[index]

    def __len__(self):
        return len(self._fields)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            f = self._fields[self._idx]
            self._idx += 1
            return f
        except IndexError:
            self._idx = 0
            raise StopIteration


class DitheredField(CompoundField):
    """ A compound field consisting of several dithered coordinates. """

    def __init__(self, name, position, dither_kwargs=None, equinox="J2000", frame="icrs",
                 **kwargs):
        """
        Args:
            name (str): The name of the field (e.g. target name).
            position (str or SkyCoord): The coordinates of the field centre.
            dither_kwargs (dict, optional): Parsed to dither.get_dither_positions. Default: None.
            equinox (str, optional): The equinox, parsed to astropy.coordinates.SkyCoord.
                Default: J2000.
            frame (str, option): The frame to be parsed to astropy.coordinates.SkyCoord.
                Default: icrs.
            **kwargs: Parsed to AbstractField.__init__.
        """
        if dither_kwargs is None:
            dither_kwargs = {}

        # Get dither coords
        centre = SkyCoord(position, equinox=equinox, frame=frame)
        coords = dither.get_dither_positions(centre, **dither_kwargs)

        # Make dithered field configs
        field_configs = []
        for i, coord in enumerate(coords):
            dither_name = f"{name}_{i}"
            field_configs.append(dict(position=coord, name=dither_name))

        # Initialise compound field
        super().__init__(name, field_configs, equinox=equinox, frame=frame, **kwargs)
