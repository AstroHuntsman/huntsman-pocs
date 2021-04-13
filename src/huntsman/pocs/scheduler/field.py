from astroplan import FixedTarget
from astropy.coordinates import SkyCoord

from panoptes.pocs.base import PanBase

from huntsman.pocs.utils import dither


class AbstractField(PanBase):

    def __init__(self, name, equinox="J2000", frame="icrs", **kwargs):
        """

        """
        super().__init__(**kwargs)

        self.equinox = equinox
        self.frame = frame
        self.name = name


class Field(FixedTarget, AbstractField):

    def __init__(self, name, position, **kwargs):
        """

        """
        AbstractField.__init__(self, name=name, **kwargs)

        # Initialise the FixedTarget base class
        if isinstance(position, SkyCoord):
            coord = position
        else:
            coord = SkyCoord(position, equinox=self.equinox, frame=self.frame)
        super().__init__(coord, name=name, **kwargs)

        # Prepare the field name
        self._field_name = self.name.title().replace(' ', '').replace('-', '')
        if not self._field_name:
            raise ValueError('Name is empty.')

    @property
    def field_name(self):
        """ Flattened field name appropriate for paths """
        return self._field_name

    def __str__(self):
        return self.name


class CompoundField(AbstractField):
    """ An iterable, indexable class consisting of several fields. """

    def __init__(self, name, field_config_list, field_class=Field):
        """

        """
        self._idx = 0

        self._fields = []
        for field_config in field_config_list:
            self._fields.append(field_class(**field_config))

    def __getitem__(self, index):
        return self._fields[index]

    def __len__(self):
        return len(self._fields)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self._fields[self._idx]
        except IndexError:
            self._idx = 0
            raise StopIteration


class DitheredField(CompoundField):
    """ A compound field consisting of several dithered coordinates. """

    def __init__(self, name, position, dither_kwargs=None, **kwargs):
        """

        """
        if dither_kwargs is None:
            dither_kwargs = {}

        # Get dither coords
        centre = SkyCoord(position, equinox=self.equinox, frame=self.frame)
        coords = dither.get_dither_positions(centre, **dither_kwargs)

        # Make dithered field configs
        field_configs = []
        for i, coord in enumerate(coords):
            dither_name = f"{self.name}_{i}"
            field_configs.append(dict(position=coord, name=dither_name))

        # Initialise compound field
        super().__init__(name, field_configs, **kwargs)


class OffsetSkyField(CompoundField):
    """ A compound field consisting of a target and sky field. """

    def __init__(self, target_config, sky_config, **kwargs):
        """

        """
        super().__init__([target_config, sky_config], **kwargs)

    @property
    def target_field(self):
        return self[0]

    @property
    def sky_field(self):
        return self[1]
