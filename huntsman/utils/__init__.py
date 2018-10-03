import os
from pocs.utils.config import load_config as config_loader


def load_config():
    config_dir = os.path.join(
        os.environ['HUNTSMAN_POCS'],
        'conf_files',
    )
    config_files = [
        os.path.join(config_dir, 'huntsman.yaml')
    ]
    config = config_loader(config_files=config_files)
    return config
