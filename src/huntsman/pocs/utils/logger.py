import os
from panoptes.pocs.utils.logger import get_logger

logger = get_logger(
    console_log_file='huntsman.log',
    full_log_file='huntsman_{time:YYYYMMDD!UTC}.log',
    log_dir=os.getenv('HUNTSMAN_DIR', '/var/huntsman/logs')
)
# See messages from underlying panoptes modules.
logger.enable('panoptes')
