#Testing...
import pytest

#import huntsman.utils.hue_light_control

def test_get_username():
    light = Hue_Lights
    user = light.get_username()
    
    return(print(user))
    

    
   

def new():
    yamlf = "/Users/SC09015/Desktop/Astro/Code/huntsman-pocs/conf_files/set_lights.yaml"
    with open(yamlf, 'r') as yml:
        try:
            newyml = (yaml.load(yml))
            hue_ip = newyml['hue_lights'][0]['hue_ip']
            file_path = newyml['hue_lights'][1]['file_path']
            led_index = newyml['hue_lights'][2]['index']['led_index']
            desk_index = newyml['hue_lights'][2]['index']['desk_index']
            flat_index = newyml['hue_lights'][2]['index']['flat_index']
            
        except yaml.YAMLError as error:
            print(error)
            
    return(hue_ip, file_path)            
                
