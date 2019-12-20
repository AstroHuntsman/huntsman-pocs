import os
from pocs.utils import listify
from pocs.utils.config import load_config as config_loader
from panoptes.utils.config import client
from huntsman.utils.pyro import get_own_ip

#==============================================================================

def query_config_server(logger=None, *args, **kwargs):
    '''
    Query the config server using the IP of the client as the key.
    '''
    try:
        key = get_own_ip()
        config = client.get_config(key, *args, **kwargs)
    except Exception as e:
        msg = f'Unable to retrieve config file from server: {e}'
        if logger is not None:
            logger.error(msg)
        else:
            print(msg)
        raise(e)
    return config
        
        
def load_config(config_files=None, **kwargs):
    '''
    
    '''
    config_dir = os.path.join(os.environ['HUNTSMAN_POCS'], 'conf_files')
    
    if config_files is None:
        config_files = ['huntsman.yaml']
        
    config_files = listify(config_files)
    config_files = [os.path.join(config_dir, config_file) for config_file in config_files]

    config = config_loader(config_files=config_files, **kwargs)
    return config

#==============================================================================
