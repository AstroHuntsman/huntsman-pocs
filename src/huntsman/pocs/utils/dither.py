import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord, SkyOffsetFrame, ICRS

# Pattern for dice 9 3x3 grid (sequence of (RA offset, dec offset) pairs)
dice9 = ((0, 0),
         (0, 1),
         (1, 1),
         (1, 0),
         (1, -1),
         (0, -1),
         (-1, -1),
         (-1, 0),
         (-1, 1))

# Pattern for dice 5 grid (sequence of (RA offset, dec offset) pairs)
dice5 = ((0, 0),
         (1, 1),
         (1, -1),
         (-1, -1),
         (-1, 1))


def get_dither_positions(base_position, n_positions=9, pattern=dice9, pattern_offset=20 * u.arcsec,
                         random_offset=None):
    """
    Given a base position creates a SkyCoord list of dithered sky positions, applying a dither
    pattern and/or random dither offsets.
    Args:
         base_position (SkyCoord or compatible): base position for the dither pattern, either a
            SkyCoord or an object
             that can be converted to one by the SkyCoord constructor (e.g. string)
         n_positions (int): number of dithered sky positions to generate
         pattern (sequence of 2-tuples, optional): sequence of (RA offset, dec offset) tuples, in
            units of the
             pattern_offset. If given pattern_offset must also be specified.
         pattern_offset (Quantity, optional): scale for the dither pattern. Should be a Quantity
            with angular units, if a numeric type is passed instead it will be assumed to be in
            arceconds. If pattern offset is given pattern must be given too.
         random_offset (Quantity, optional): scale of the random offset to apply to both RA and dec.
            Should be a Quantity with angular units, if numeric type passed instead it will be
            assumed to be in arcseconds.
    Returns:
        SkyCoord: list of n_positions dithered sky positions
    """
    if not isinstance(base_position, SkyCoord):
        try:
            base_position = SkyCoord(base_position)
        except ValueError:
            raise ValueError(f"Base position {base_position} could not be converted to SkyCoord")

    if pattern:
        if pattern_offset is None:
            raise ValueError("`pattern` specified but no `pattern_offset` given!")

        if not isinstance(pattern_offset, u.Quantity):
            pattern_offset = pattern_offset * u.arcsec

        pattern_length = len(pattern)

        RA_offsets = [pattern[count % pattern_length][0]
                      for count in range(n_positions)] * pattern_offset
        dec_offsets = [pattern[count % pattern_length][1]
                       for count in range(n_positions)] * pattern_offset

    else:
        RA_offsets = np.zeros(n_positions) * u.arcsec
        dec_offsets = np.zeros(n_positions) * u.arcsec

    if random_offset is not None:
        if not isinstance(random_offset, u.Quantity):
            random_offset = random_offset * u.arcsec

        RA_offsets += np.random.uniform(low=-1, high=+1, size=RA_offsets.shape) * random_offset
        dec_offsets += np.random.uniform(low=-1, high=+1, size=dec_offsets.shape) * random_offset

    offsets = SkyOffsetFrame(lon=RA_offsets, lat=dec_offsets, origin=base_position)
    positions = offsets.transform_to(ICRS)

    return SkyCoord(positions)
