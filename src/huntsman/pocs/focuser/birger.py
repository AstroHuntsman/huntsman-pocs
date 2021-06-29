from huntsman.pocs.focuser.serial import HuntsmanSerialFocuser
from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser


class Focuser(BirgerFocuser, HuntsmanSerialFocuser):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
