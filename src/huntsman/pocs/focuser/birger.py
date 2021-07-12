from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser
from huntsman.pocs.focuser import HuntsmanFocuser


class Focuser(BirgerFocuser, HuntsmanFocuser):
    """ Override class to use methods in HuntsmanFocuser. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _initialize(self):
        """ Initialize the Birger focuser. """
        # Set 'verbose' and 'legacy' response modes. The response from this depends on
        # what the current mode is... but after a power cycle it should be 'rm1,0', 'OK'
        self._send_command('rm1,0', response_length=0)

        # Set the serial number
        self._serial_number = self._get_serial_number()

        # Get the version string of the adaptor software libray. Accessible as self.library_version
        self._get_library_version()

        # Get the hardware version of the adaptor. Accessible as self.hardware_version
        self._get_hardware_version()

        # Get basic lens info (e.g. '400mm,f28' for a 400 mm, f/2.8 lens). Accessible as
        # self.lens_info
        self._get_lens_info()

        # Initialise the aperture motor. This also has the side effect of fully opening the iris.
        self._initialise_aperture()

        # Initalise focus. First move the focus to the close stop.
        self._move_zero()

        # Then reset the focus encoder counts to 0
        self._zero_encoder()
        self._min_position = 0

        # Calibrate the focus with the 'Learn Absolute Focus Range' command
        self._learn_focus_range()

        # Finally move the focus to the far stop (close to where we'll want it) and record position
        self._max_position = self._move_inf()
