
from pocs.dome.bisque import Dome as BisqueDome
from pocs.dome.abstract_serial_dome import AbstractSerialDome


class HuntsmanDome(AbstractSerialDome, BisqueDome):
    """Short summary.

    Parameters
    ----------
    *args : type
        Description of parameter `*args`.
    **kwargs : type
        Description of parameter `**kwargs`.

    Attributes
    ----------
    dome : type
        Description of attribute `dome`.

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def open_dome(self):
        """Short summary.

        Returns
        -------
        type
            Description of returned object.

        """
        if not self.dome:
            return True
        if not self.dome.connect():
            print("Not connected to Musca")
            return False
        if not self.dome.is_open:
            self.logger.info('Opening dome')
        return self.dome.open()

    def close_dome(self):
        """Short summary.

        Returns
        -------
        type
            Description of returned object.

        """
        if not self.dome:
            return True
        if not self.dome.connect():
            print("Not connected to Musca")
            return False
        if not self.dome.is_closed:
            self.logger.info('Closed dome')
        return self.dome.close()

    @property
    def status(self):
        """Short summary.

        Returns
        -------
        type
            Description of returned object.

        """
        if not self.dome.is_connected:
            return "Not connected to th dome"
        if self.dome.is_open:
            return "The dome is open."
        if self.dome.is_closed:
            return "The dome is closed."
