#Testing...
import pytest
import huntsman.utils.hue_light_control


def test_get_username():
    light = Hue_Lights()
    users = light.get_username()
    assert (users)
    
def test_login():
    light = Hue_Lights()
    login = light.login()
    
def test_import_yaml():
    yaml_params = import_yaml()
    assert yaml_params
    
def test_get_index():
    light = Hue_Lights
    index = light.get_index
    
    return(print(index))
    

    
