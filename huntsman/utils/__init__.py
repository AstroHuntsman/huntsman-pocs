import os
from pocs.utils import listify
from pocs.utils.config import load_config as config_loader


def load_config(config_files=None, **kwargs):
    config_dir = os.path.join(
        os.environ['HUNTSMAN_POCS'],
        'conf_files',
    )
    if config_files is None:
        config_files = ['huntsman.yaml']
    config_files = listify(config_files)
    config_files = [os.path.join(config_dir, config_file) for config_file in config_files]

    config = config_loader(config_files=config_files, **kwargs)
    return config
