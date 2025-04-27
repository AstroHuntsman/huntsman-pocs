import os
from panoptes.pocs.mount import create_mount_simulator
from huntsman.pocs.utils.huntsman import create_huntsman_pocs
from huntsman.pocs.dome import create_dome_simulator


os.environ["POCSTIME"] = "2020-10-09 08:30:00"

mount = create_mount_simulator()
dome = create_dome_simulator()

pocs = create_huntsman_pocs(mount=mount, dome=dome, simulators=["power", "weather"], with_dome=True, with_autoguider=False)

pocs.run()
