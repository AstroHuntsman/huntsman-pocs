
# coding: utf-8

# In[1]:

from __future__ import print_function
import yaml
from ipywidgets import interact, interactive, fixed, interact_manual
import ipywidgets as widgets
from IPython.display import display
import os
import datetime


# In[2]:

device_data = {'serial_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
               'camera_into_serial_port': [1, 2, 3, 4],
               'USBhub_SN': ['OX518EFFE1', 'OXCD12637D'],
               'camera_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
               'sbig_SN': ['83F011167', '83F011791', '83F011639', '83F010801', '83F010774', '83F011758', '83F010771', '83F011810'],
               'birger_SN': ['10858', '14287', '14286', '14285', '13281', '13134', '14284', '13208', '14276'],
               'lens_SN': ['3360000099', '3360000063', '3360000087', '2850000067', '3150000110', '5370000054'],
               'filter_ID': ['r2_1', 'r2_2', 'g2_3', 'g2_4', 'r2_5', 'r2_6', 'r2_7', 'g2_8', 'g2_9', 'ha1_10', 'ha1_11', 'g2_12', 'ha1_13', 'ha1_14']
               }


# In[3]:

with open('serial_management.yaml', 'w') as file:
    yaml.dump(device_data)
    file.write(yaml.dump(device_data))

with open('serial_management.yaml', 'r') as file:
    data = yaml.load(file)


# In[4]:

def type_filename(type_filename_here):
    return type_filename_here


# In[5]:

file_name = interactive(type_filename, type_filename_here="filename.yaml")


# In[6]:

data_list = {'name': 'HuntsmanSSO',
             'log_file': 'huntsman',
             'location': {'name': 'Siding Spring Observatory',
                          'latitude': -31.27,  # degrees
                          'longitude': 149.06,  # Degrees
                          'elevation': 1000.0,  # Meters
                          'utc_offset': 10.00,  # Hours
                          'horizon': 30,  # Degrees
                          'timezone': 'Australia/Sydney'
                          },
             'scheduler': {'type': 'dispatch',
                           'fields_file': 'targets.yaml'},
             'dome': {'template_dir': 'resources/bisque'},
             'guider': {'template_dir': 'resources/bisque/guider',
                        'image_path': '/tmp/guide_image.fits',
                        'bin_size': 1},
             'mount': {'brand': 'bisque',
                       'model': 45,
                       'driver': 'bisque',
                       'template_dir': 'resources/bisque'},
             'pointing': {'threshold': 0.05,
                          'exp_time': 30,
                          'max_iterations': 3},
             'state_machine': 'huntsman',
             'directories': {'base': '/var/huntsman', 'images': 'images',
                              'webcam': 'webcams', 'data': 'data',
                              'resources': 'POCS/resources/',
                              'targets': '/var/huntsman/huntsman-pocs/conf_files',
                              'mounts': 'POCS/resources/mounts'
                             },
             'cameras': {'hdr_mode': True,
                         'auto_detect': False,
                         'devices': [None]}}


# In[7]:

def a(birger_serial_number):
    return birger_serial_number


def b(sbig_serial_number):
    return sbig_serial_number


def c(lens_serial_number):
    return lens_serial_number


def d(filter_ID_code):
    return filter_ID_code


def e(serial_into_USBhub_port):
    return serial_into_USBhub_port


def f(camera_into_serial_port):
    return camera_into_serial_port


def j(USBhub_SN):
    return USBhub_SN


def k(camera_into_USBhub_port):
    return camera_into_USBhub_port


# In[8]:

birger_sn = data['birger_SN']
birger_serial_number = interactive(a, birger_serial_number=birger_sn)
sbig_sn = data['sbig_SN']
sbig_serial_number = interactive(b, sbig_serial_number=sbig_sn)
lens_sn = data['lens_SN']
lens_serial_number = interactive(c, lens_serial_number=lens_sn)
filter_ID = data['filter_ID']
filter_ID_code = interactive(d, filter_ID_code=filter_ID)
serial_into_USBhub = data['serial_into_USBhub_port']
serial_into_USBhub_port = interactive(e, serial_into_USBhub_port=serial_into_USBhub)
camera_into_serial = data['camera_into_serial_port']
camera_into_serial_port = interactive(f, camera_into_serial_port=camera_into_serial)
USBhub = data['USBhub_SN']
USBhub_SN = interactive(j, USBhub_SN=USBhub)
camera_into_USBhub = data['camera_into_USBhub_port']
camera_into_USBhub_port = interactive(k, camera_into_USBhub_port=camera_into_USBhub)


# In[9]:

def h(add_device):
    birger_SN = birger_serial_number.result
    sbig_SN = sbig_serial_number.result
    lens_SN = lens_serial_number.result
    filter_ID = filter_ID_code.result
    serial_to_USBhub_port = serial_into_USBhub_port.result
    camera_to_serial_port = camera_into_serial_port.result
    USB_hub_SN = USBhub_SN.result
    camera_to_USBhub_port = camera_into_USBhub_port.result

    lens_name_dict = {'3360000099': 'name1', '3360000063': 'name2',
                      '3360000087': 'name3', '2850000067': 'name4',
                      '3150000110': 'name5', '5370000054': 'name6'}

    additional_device = {'model': 'sbig',
                         'port': sbig_SN,
                         'filter_type': filter_ID,
                         'focuser': {'model': 'birger',
                                     'port': birger_SN

                                     },
                         'lens': {'model': 'canon',
                                  'port': lens_SN},
                         'USB_hub_serial_number': USB_hub_SN,
                         'camera_into_serial_adaptor_port': camera_to_serial_port,
                         'serial_adaptor_into_USBhub_port': serial_to_USBhub_port,
                         'camera_into_USBhub_port': camera_to_USBhub_port
                         }
    if data_list['cameras']['devices'] == [None]:
        data_list['cameras']['devices'] = [additional_device]
    else:
        data_list['cameras']['devices'].append(additional_device)
    return (add_device)


# In[10]:

date_info = datetime.datetime.today()
datetime_str = date_info.strftime('%Y_%m_%d_%H_%M')

archive_filename = '{}_{}.{}'.format('huntsman', datetime_str, 'yaml')


# In[11]:

archive_filename


# In[12]:

def g(create_file):
    strOutFile1 = os.path.join("/var/huntsman-pocs/conf_files", 'huntsman.yaml')
    objFile1 = open(strOutFile1, "w")
    yaml.dump(data_list, objFile1, default_flow_style=False, indent=4)
    objFile1.close()

    strOutFile = os.path.join("/var/huntsman-pocs/conf_files/huntsman_archive", archive_filename)
    objFile = open(strOutFile, "w")
    yaml.dump(data_list, objFile, default_flow_style=False, indent=4)
    objFile.close()

    return create_file


# In[14]:

# display(file_name)

display(birger_serial_number)
display(sbig_serial_number)
display(lens_serial_number)
display(filter_ID_code)
display(serial_into_USBhub_port)
display(camera_into_serial_port)
display(USBhub_SN)
display(camera_into_USBhub_port)

button1 = widgets.Button(description="Add new device set")
display(button1)
button1.on_click(h)

button = widgets.Button(description="Save File")
display(button)
button.on_click(g)
