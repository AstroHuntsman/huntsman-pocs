import yaml
import os
import datetime
import ipywidgets as widgets
from ipywidgets import interact, interactive, fixed, interact_manual
from IPython.display import display

def birger_sn_widget(birger_serial_number):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        birger_serial_number (str) : the serial number of the birger device as selected from the widget.

    Returns:
        The result of the widget; the chosen focuser serial number

    """
    return birger_serial_number

def camera_sn_widget(camera_serial_number):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_serial_number (str) : the serial number of the camera device as selected from the widget.

    Returns:
        The result of the widget; the chosen camera serial number

    """
    return camera_serial_number

def lens_sn_widget(lens_serial_number):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        lens_serial_number (str) : the serial number of the lens device as selected from the widget.

    Returns:
        The result of the widget; the chosen lens serial number

    """
    return lens_serial_number

def filter_ID_widget(filter_ID_code):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        filter_ID_code (str) : the ID number of the lens as selected from the widget.

    Returns:
        The result of the widget; the chosen filter ID number

    """
    return filter_ID_code

def serial_to_usb_widget(serial_into_USBhub_port):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        serial_into_USBhub_port (str) : the port number of the USB Hub that the Serial Adaptor is plugged into as selected from the widget.

    Returns:
        The result of the widget; the chosen USB port number

    """
    return serial_into_USBhub_port

def camera_to_serial_widget(camera_into_serial_port):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_into_serial_port (str) : the port number of the Serial Adaptor that the camera is plugged into as selected from the widget.

    Returns:
        The result of the widget; the chosen serial port number

    """
    return camera_into_serial_port

def usbhub_sn_widget(USBhub_SN):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        USBhub_SN (str) : the serial number of the USB Hub as selected from the widget.

    Returns:
        The result of the widget; the chosen USB Hub serial number

    """
    return USBhub_SN

def camera_to_usb_widget(camera_into_USBhub_port):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_into_USBhub_port (str) : the port number of the USB Hub that the camera is plugged into as selected from the widget.

    Returns:
        The result of the widget; the chosen USB port number

    """
    return camera_into_USBhub_port



def create_yaml_file(local_directory='/var/huntsman-pocs/conf_files', archive_directory='/var/huntsman-pocs/conf_files/huntsman_archive'):
    """This function runs all the code to generate the .yaml config files for the Huntsman-POCS system.
    It displays the Jupyter widgets which the user can interact with to write and save the config files.

    Files are saved in two locations, one for the local file that POCS will access, and the other is an archive of all previous config files which acts as a version control.
    By default, these locations are:
        '/var/huntsman-pocs/conf_files/huntsman.yaml' for the local file.
        '/var/huntsman-pocs/conf_files/huntsman_archive/huntsman_YYYY_mm_dd_hh_MM.yaml' for the archive file.

    Steps for the user to follow:
        Select from the dropdown menus the information for one device set.
        Click 'Add new device set'.
        Select from the dropdown menus the information for the next device set.
        Click 'Add new device set'.
        Repeat until all device sets have been added.
        Click 'Save File' to write the .yaml file.

    Args:
        local_directory : the path of the directory where the config file accessed by POCS will be saved.
        archive_directory : the path of the directory where all the archived config files are.

    Displays:
        Jupyter widgets of drop-down menus to select the device sets.
            These widgets are used to generate and save the .yaml config files.

    Output:
        A .yaml config file for Huntsman

    """

    data = {'serial_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
            'camera_into_serial_port': [1, 2, 3, 4],
            'USBhub_SN': ['OX518EFFE1', 'OXCD12637D'],
            'camera_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
            'camera_SN': ['83F011167', '83F011791', '83F011639', '83F010801',
                          '83F010774', '83F011758', '83F010771', '83F011810', 'ML5232816', 'ML1722016'],
            'birger_SN': ['10858', '14287', '14286', '14285', '13281', '13134', '14284', '13208', '14276'],
            'lens_SN': ['3360000099', '3360000063', '3360000087', '2850000067', '3150000110', '5370000054'],
            'filter_ID': ['r2_1', 'r2_2', 'g2_3', 'g2_4', 'r2_5', 'r2_6', 'r2_7', 'g2_8', 'g2_9', 'ha1_10',
                          'ha1_11', 'g2_12', 'ha1_13', 'ha1_14']
            }

    previous_file = os.path.join(local_directory, 'huntsman.yaml')
    # check that this is the correct file path for Huntsman-POCS
    # loading general data from the previous .yaml file used
    with open(previous_file, 'r') as file:
        data_list = yaml.load(file)

    if 'cameras' in data_list:
        del data_list['cameras']

    data_list.update({'cameras': {'hdr_mode': True, 'auto_detect': False, 'devices': [None]}})


    birger_sn = data['birger_SN']
    birger_serial_number = interactive(birger_sn_widget, birger_serial_number=birger_sn)
    camera_sn = data['camera_SN']
    camera_serial_number = interactive(camera_sn_widget, camera_serial_number=camera_sn)
    lens_sn = data['lens_SN']
    lens_serial_number = interactive(lens_sn_widget, lens_serial_number=lens_sn)
    filter_ID = data['filter_ID']
    filter_ID_code = interactive(filter_ID_widget, filter_ID_code=filter_ID)
    serial_into_USBhub = data['serial_into_USBhub_port']
    serial_into_USBhub_port = interactive(
        serial_to_usb_widget, serial_into_USBhub_port=serial_into_USBhub)
    camera_into_serial = data['camera_into_serial_port']
    camera_into_serial_port = interactive(
        camera_to_serial_widget, camera_into_serial_port=camera_into_serial)
    USBhub = data['USBhub_SN']
    USBhub_SN = interactive(usbhub_sn_widget, USBhub_SN=USBhub)
    camera_into_USBhub = data['camera_into_USBhub_port']
    camera_into_USBhub_port = interactive(
        camera_to_usb_widget, camera_into_USBhub_port=camera_into_USBhub)

    birger_SN = birger_serial_number.result
    camera_SN = camera_serial_number.result
    lens_SN = lens_serial_number.result
    filter_ID = filter_ID_code.result
    serial_to_USBhub_port = serial_into_USBhub_port.result
    camera_to_serial_port = camera_into_serial_port.result
    USB_hub_SN = USBhub_SN.result
    camera_to_USBhub_port = camera_into_USBhub_port.result


    date_info = datetime.datetime.today()
    datetime_str = date_info.strftime('%Y_%m_%d_%H_%M')
    archive_filename = '{}_{}.{}'.format('huntsman', datetime_str, 'yaml')


    display(birger_serial_number)
    display(camera_serial_number)
    display(lens_serial_number)
    display(filter_ID_code)
    display(serial_into_USBhub_port)
    display(camera_into_serial_port)
    display(USBhub_SN)
    display(camera_into_USBhub_port)

    button1 = widgets.Button(description="Add new device set")
    display(button1)
    button1.on_click(add_device_widget)

    button = widgets.Button(description="Save File")
    display(button)
    button.on_click(save_file_widget)





# birger_SN = birger_serial_number.result
# camera_SN = camera_serial_number.result
# lens_SN = lens_serial_number.result
# filter_ID = filter_ID_code.result
# serial_to_USBhub_port = serial_into_USBhub_port.result
# camera_to_serial_port = camera_into_serial_port.result
# USB_hub_SN = USBhub_SN.result
# camera_to_USBhub_port = camera_into_USBhub_port.result

def add_device_widget(add_device):
    """Function to add the details selected using the drop-down menu widgets to the 'data_list' dictionary.
    The function is called by the widget and is then run when the user clicks on the widget button.

    Args:
        add_device : on clicking the widget, a device set is saved to the dict.

    Returns:
        Appends the data_list dict with the information chosen from the device information widgets

    """

    lens_name_dict = {'3360000099': 'name1', '3360000063': 'name2',
                      '3360000087': 'name3', '2850000067': 'name4',
                      '3150000110': 'name5', '5370000054': 'name6'}
    # need to put the lens names in the above dict when they are finalised

    lens_image_stabalisation = {'3360000099': True, '3360000063': True,
                                '3360000087': True, '2850000067': True,
                                '3150000110': True, '5370000054': False}

    camera_dict = {'83F011167': 'sbig', '83F011791': 'sbig', '83F011639': 'sbig',
                   '83F010801': 'sbig', '83F010774': 'sbig', '83F011758': 'sbig',
                   '83F010771': 'sbig', '83F011810': 'sbig', 'ML5232816': 'fli', 'ML1722016': 'fli'}

    additional_device = {'model': camera_dict[camera_SN],
                         'port': camera_SN,
                         'filter_type': filter_ID,
                         'focuser': {'model': 'birger',
                                     'port': birger_SN

                                     },
                         'lens': {'model': 'canon',
                                  'port': lens_SN,
                                  'name': lens_name_dict[lens_SN],
                                  'image_stabalisataion': lens_image_stabalisation[lens_SN]},
                         'USB_hub_serial_number': USB_hub_SN,
                         'camera_into_serial_adaptor_port': camera_to_serial_port,
                         'serial_adaptor_into_USBhub_port': serial_to_USBhub_port,
                         'camera_into_USBhub_port': camera_to_USBhub_port
                         }
    if data_list['cameras']['devices'] == [None]:
        data_list['cameras']['devices'] = [additional_device]
    else:
        data_list['cameras']['devices'].append(additional_device)


def save_file_widget(create_file):
    """This function writes the 'data_list' dictionary to a .yaml text file.
    The function is called by the widget and is run when the user clicks on the widget button.

    Args:
        create_file : on clicking the widget, the dict is saved to a .yaml file

    Returns:
        Writes the information in the dict into a .yaml file in two locations;
            '/var/huntsman-pocs/conf_files/huntsman.yaml'
                for the local config file to be used by POCS

                and

            '/var/huntsman-pocs/conf_files/huntsman_archive/huntsman_YYYY_mm_dd_hh_MM.yaml'
                for the archive of all version of the config files, with the date it was created in the filename

    """

    strOutFile1 = os.path.join(local_directory, 'huntsman.yaml')
    objFile1 = open(strOutFile1, "w")
    yaml.dump(data_list, objFile1, default_flow_style=False, indent=4)
    objFile1.close()

    strOutFile = os.path.join(archive_directory, archive_filename)
    objFile = open(strOutFile, "w")
    yaml.dump(data_list, objFile, default_flow_style=False, indent=4)
    objFile.close()


# def create_yaml_file(local_directory='/var/huntsman-pocs/conf_files', archive_directory='/var/huntsman-pocs/conf_files/huntsman_archive'):
#     """This function runs all the code to generate the .yaml config files for the Huntsman-POCS system.
#     It displays the Jupyter widgets which the user can interact with to write and save the config files.
#
#     Files are saved in two locations, one for the local file that POCS will access, and the other is an archive of all previous config files which acts as a version control.
#     By default, these locations are:
#         '/var/huntsman-pocs/conf_files/huntsman.yaml' for the local file.
#         '/var/huntsman-pocs/conf_files/huntsman_archive/huntsman_YYYY_mm_dd_hh_MM.yaml' for the archive file.
#
#     Steps for the user to follow:
#         Select from the dropdown menus the information for one device set.
#         Click 'Add new device set'.
#         Select from the dropdown menus the information for the next device set.
#         Click 'Add new device set'.
#         Repeat until all device sets have been added.
#         Click 'Save File' to write the .yaml file.
#
#     Args:
#         local_directory : the path of the directory where the config file accessed by POCS will be saved.
#         archive_directory : the path of the directory where all the archived config files are.
#
#     Displays:
#         Jupyter widgets of drop-down menus to select the device sets.
#             These widgets are used to generate and save the .yaml config files.
#
#     Output:
#         A .yaml config file for Huntsman
#
#     """
#
#     data = {'serial_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
#             'camera_into_serial_port': [1, 2, 3, 4],
#             'USBhub_SN': ['OX518EFFE1', 'OXCD12637D'],
#             'camera_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
#             'camera_SN': ['83F011167', '83F011791', '83F011639', '83F010801',
#                           '83F010774', '83F011758', '83F010771', '83F011810', 'ML5232816', 'ML1722016'],
#             'birger_SN': ['10858', '14287', '14286', '14285', '13281', '13134', '14284', '13208', '14276'],
#             'lens_SN': ['3360000099', '3360000063', '3360000087', '2850000067', '3150000110', '5370000054'],
#             'filter_ID': ['r2_1', 'r2_2', 'g2_3', 'g2_4', 'r2_5', 'r2_6', 'r2_7', 'g2_8', 'g2_9', 'ha1_10',
#                           'ha1_11', 'g2_12', 'ha1_13', 'ha1_14']
#             }
#
#     previous_file = os.path.join(local_directory, 'huntsman.yaml')
#     # check that this is the correct file path for Huntsman-POCS
#     # loading general data from the previous .yaml file used
#     with open(previous_file, 'r') as file:
#         data_list = yaml.load(file)
#
#     if 'cameras' in data_list:
#         del data_list['cameras']
#
#     data_list.update({'cameras': {'hdr_mode': True, 'auto_detect': False, 'devices': [None]}})
#
#
#     birger_sn = data['birger_SN']
#     birger_serial_number = interactive(birger_sn_widget, birger_serial_number=birger_sn)
#     camera_sn = data['camera_SN']
#     camera_serial_number = interactive(camera_sn_widget, camera_serial_number=camera_sn)
#     lens_sn = data['lens_SN']
#     lens_serial_number = interactive(lens_sn_widget, lens_serial_number=lens_sn)
#     filter_ID = data['filter_ID']
#     filter_ID_code = interactive(filter_ID_widget, filter_ID_code=filter_ID)
#     serial_into_USBhub = data['serial_into_USBhub_port']
#     serial_into_USBhub_port = interactive(
#         serial_to_usb_widget, serial_into_USBhub_port=serial_into_USBhub)
#     camera_into_serial = data['camera_into_serial_port']
#     camera_into_serial_port = interactive(
#         camera_to_serial_widget, camera_into_serial_port=camera_into_serial)
#     USBhub = data['USBhub_SN']
#     USBhub_SN = interactive(usbhub_sn_widget, USBhub_SN=USBhub)
#     camera_into_USBhub = data['camera_into_USBhub_port']
#     camera_into_USBhub_port = interactive(
#         camera_to_usb_widget, camera_into_USBhub_port=camera_into_USBhub)
#
#     birger_SN = birger_serial_number.result
#     camera_SN = camera_serial_number.result
#     lens_SN = lens_serial_number.result
#     filter_ID = filter_ID_code.result
#     serial_to_USBhub_port = serial_into_USBhub_port.result
#     camera_to_serial_port = camera_into_serial_port.result
#     USB_hub_SN = USBhub_SN.result
#     camera_to_USBhub_port = camera_into_USBhub_port.result
#
#
#     date_info = datetime.datetime.today()
#     datetime_str = date_info.strftime('%Y_%m_%d_%H_%M')
#     archive_filename = '{}_{}.{}'.format('huntsman', datetime_str, 'yaml')
#
#
#     display(birger_serial_number)
#     display(camera_serial_number)
#     display(lens_serial_number)
#     display(filter_ID_code)
#     display(serial_into_USBhub_port)
#     display(camera_into_serial_port)
#     display(USBhub_SN)
#     display(camera_into_USBhub_port)
#
#     button1 = widgets.Button(description="Add new device set")
#     display(button1)
#     button1.on_click(add_device_widget)
#
#     button = widgets.Button(description="Save File")
#     display(button)
#     button.on_click(save_file_widget)
