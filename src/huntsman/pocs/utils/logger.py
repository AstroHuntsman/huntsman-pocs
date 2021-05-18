import os

from panoptes.pocs.utils.logger import LOGGER_INFO
from panoptes.pocs.utils.logger import get_logger as get_pocs_logger

LOGGER_INFO.handlers = {}

logger = get_pocs_logger(
    console_log_file='huntsman.log',
    full_log_file='huntsman_{time:YYYYMMDD!UTC}.log',
    log_dir=os.getenv('PANLOG', 'logs'),
    console_log_level='DEBUG',
    stderr_log_level='INFO',
)
# See messages from underlying panoptes modules.
logger.enable('panoptes')


def get_logger():
    """ Dummy function to return the logger. """
    return logger
