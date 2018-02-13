#!/usr/bin/env python
import datetime
import email
import imaplib

from warnings import warn

from astropy.coordinates import SkyCoord
from astropy.time import Time

from ....utils.config import load_config
from ....utils.too.alert_pocs import Alerter
from ....utils.too.grav_wave.grav_wave import GravityWaveEvent


class GravWaveParse(object):

    """Creates parser classe for Gravity Wave events.

    Attributes:
        - configname (str): name of config file it reads parser properies from.
        - config (python dictionary or list of dictionaries): the loaded config file
            of the given name.
        - test_message (bool): enables the reading of test messages.
        - checked_targets (list): list of final targets in the parser.
        - alert_pocs (bool): Tells the Alerter class whether or not to send checked_targets.
        - selection_criteria (dictionary): example: {'name': (srt), 'max_tiles': (float)}, determines
            when tiling is complete. If not provided, is read from config_grav.
        - observer (astroplan Observer): an observer with the location specified in the
            location config, unless observer ofjevt is given in the init.
        - altitude (float): the minimum altitude above the horizon where above which we want to be observing.
        - fov (dictionary): of format {'ra': (float), 'dec': (float)}, info about the size of the field
            of view of the telescope. If not given, is read from config_grav"
        - verbose (bool): tells the methods whether or not to print.
    """

    def __init__(
            self,
            test_message=False,
            configname='parsers_config',
            alert_pocs=True,
            *args,
            **kwargs):

        self.configname = configname

        self.config = load_config(configname)
        self.checked_targets = []

        self.alert_pocs = alert_pocs
        self.test_message = test_message

        # not sure where observer and altitude are coming from
        self.selection_criteria = kwargs.get('selection_criteria', None)
        self.observer = kwargs.get('observer', None)
        self.altitude = kwargs.get('altitude', None)
        self.fov = kwargs.get('fov', None)
        self.verbose = kwargs.get('verbose', False)

    def is_test_file(self, testing):

        tst = True
        type_of_tst = ''
        if 'G' in testing:
            tst = False
        else:
            tst = True
            if 'M' in testing:
                type_of_tst = 'M'
            elif 'T' in testing:
                type_of_tst = 'T'

        return tst, type_of_tst

    def parse_event(self, header, skymap):
        """Interprets Gravity Wave notice and creates list of targets.

        After `...` returns the python dictionary, this method craetes all the parameters
        to pass to `GravityWaveEvent`, which then handles the target creation.

        Args:
            - text (str): the body of the notice to be parsed.
        Returns:
            - list of targets. Empty if event could not be parsed, or if fundemental
                attribute misiing from the header, it will raise an error."""

        targets = []

        try:

            testing, type_of_testing = self.is_test_file(header['OBJECT'])
        except Exception as e:
            testing = True
            if self.verbose:
                warn('Could not find type of testing!')
        try:
            time = Time(float(header['MJD-OBS']), format='jd', scale='utc')
        except Exception as e:
            time = Time(0.0, format='jd', scale='utc')
            if self.verbose:
                warn('Could not find start time!')

        if testing == self.test_message:

            grav_wave = GravityWaveEvent(skymap, time=time,
                                         alert_pocs=self.alert_pocs,
                                         configname=self.configname,
                                         header=header,
                                         verbose=self.verbose,
                                         selection_criteria=self.selection_criteria,
                                         fov=self.fov,
                                         altitude=self.altitude,
                                         observer=self.observer)

            if grav_wave.created_event:
                targets = grav_wave.tile_sky()

        self.checked_targets = targets
        return targets
