import yaml
import os
import datetime
import ipywidgets as widgets
from ipywidgets import interact, interactive, fixed, interact_manual
from IPython.display import display
import sys


class POCS_devices_database(object):
    """
    This class manages serial numbers and other information of multiple devices being used with POCS.
    It can be used to display ipython widgets to select the device information, and then create a .yaml
    config file that can be read and implemented by POCS.
    """

    def __init__(self,
                 device_info_master_directory='/var/huntsman/huntsman-pocs/conf_files/',
                 device_info_master_file='device_info_master.yaml',
                 local_directory='/var/huntsman/huntsman-pocs/conf_files/',
                 archive_directory='/var/huntsman/huntsman-pocs/conf_files/archive/',
                 output_yaml_filename='huntsman.yaml'):
        """
        Sets up the location to save all files, loads information off previous files, and gets the current
        datetime info for the archive filename.

        Args:
            device_info_master_directory : the file path of where the .yaml file that all the device info is in
            local_directory : the dir where the config file needs to be saved to be used by POCS
            archive_directory : the dir where the archive/version control of the config files are kept
            output_yaml_filename : the chosen filename of the local config file used by POCS
        """
        self.local_directory = local_directory
        self.archive_directory = archive_directory
        self.device_info_master_directory = device_info_master_directory
        self.output_yaml_filename = output_yaml_filename
        self.device_info_master_file = device_info_master_file

        device_info_file = os.path.join(
            self.device_info_master_directory, self.device_info_master_file)
        try:
            with open(device_info_file, 'r') as file:
                self.data = yaml.load(file)
        except FileNotFoundError:
            sys.exit("Cannot find device information master file")

        date_info = datetime.datetime.today()
        datetime_str = date_info.strftime('%Y_%m_%d_%H_%M')
        self.archive_filename = '{}_{}.{}'.format('huntsman', datetime_str, 'yaml')

        previous_file = os.path.join(self.local_directory, self.output_yaml_filename)
        # loading general data from the previous .yaml file used
        try:
            with open(previous_file, 'r') as file:
                self.data_dict = yaml.load(file)
            if self.data_dict is not None and 'cameras' in self.data_dict:
                del self.data_dict['cameras']
        except FileNotFoundError:
            self.data_dict = {}

        self.data_dict.update(
            {'cameras': {'hdr_mode': True, 'auto_detect': False, 'devices': [None]}})

    def add_device_widget(self, dummy_variable_for_widget):
        """Function to add the details selected using the drop-down menu widgets to the 'data_dict'
        dictionary.
        The function is called by a widget in start_interface() and is then run when the user clicks
        on the widget button.

        Args:
            dummy_variable_for_widget : the widget needs an extra arg for some reason

        Output:
            Appends the data_dict dict with the information chosen from the device information widgets.

        """

        additional_device = {'model': self.camera_type_chosen,
                             'port': self.camera_sn_chosen,
                             'filter_type': self.filter_ID_chosen,
                             'focuser': {'model': 'birger',
                                         'port': self.birger_sn_chosen

                                         },
                             'lens': {'model': 'canon',
                                      'port': self.lens_sn_chosen,
                                      'name': self.lens_name_chosen,
                                      'image_stabalisataion': self.lens_image_stabalisation_chosen},
                             'USB_hub_serial_number': self.USB_hub_SN_chosen,
                             'camera_into_serial_adaptor_port': self.camera_to_serial_port_chosen,
                             'serial_adaptor_into_USBhub_port': self.serial_to_USBhub_port_chosen,
                             'camera_into_USBhub_port': self.camera_to_USBhub_port_chosen
                             }

        if self.data_dict['cameras']['devices'] == [None]:
            self.data_dict['cameras']['devices'] = [additional_device]
        else:
            self.data_dict['cameras']['devices'].append(additional_device)

        return self.data_dict

    def save_file(self, dummy_variable_for_widget):
        """This function writes the 'data_dict' dictionary to a .yaml text file.
        The function is called by a widget in start_interface() and is run when the user clicks on the
        widget button.

        Args:
            dummy_variable_for_widget : the widget needs an extra arg for some reason

        Output:
            Writes the information in the dict into a .yaml file in two locations, as determined by the
            assign_local_dir() and assign_archive_dir methods.
            The default locations are:
                '/var/huntsman/huntsman-pocs/conf_files/huntsman.yaml'
                    for the local config file to be used by POCS

                    and

                '/var/huntsman/huntsman-pocs/conf_files/huntsman_archive/huntsman_YYYY_mm_dd_hh_MM.yaml'
                    for the archive of all version of the config files, with the date it was created in
                    the filename

        """

        strOutFile1 = os.path.join(self.local_directory, self.output_yaml_filename)
        objFile1 = open(strOutFile1, "w")
        yaml.dump(self.data_dict, objFile1, default_flow_style=False, indent=4)
        objFile1.close()

        strOutFile = os.path.join(self.archive_directory, self.archive_filename)
        objFile = open(strOutFile, "w")
        yaml.dump(self.data_dict, objFile, default_flow_style=False, indent=4)
        objFile.close()

    def start_interface(self):
        """This function runs all the code to generate the .yaml config files for the Huntsman-POCS system.
        It displays the Jupyter widgets which the user can interact with to write and save the config files.

        Files are saved in two locations, one for the local file that POCS will access,
                        and the other is an archive of all previous config files which acts as a version control.
        By default, these locations are: (but can be changed using the arguments in the __init__ method)
            '/var/huntsman/huntsman-pocs/conf_files/huntsman.yaml' for the local file.
            '/var/huntsman/huntsman-pocs/conf_files/huntsman_archive/huntsman_YYYY_mm_dd_hh_MM.yaml' for the archive file.

        Steps for the user to follow:
            Select from the dropdown menus the information for one device set.
            Click 'Add new device set'.
            Select from the dropdown menus the information for the next device set.
            Click 'Add new device set'.
            Repeat until all device sets have been added.
            Click 'Save File' to write the .yaml file.

        Displays:
            Jupyter widgets of drop-down menus to select the device sets.
                These widgets are used to generate and save the .yaml config files.

        Output:
            A .yaml config file for Huntsman

        """
        print(self.start_interface.__doc__)

        birger_sn = self.data['birger_SN']
        self.birger_serial_number = interactive(
            birger_sn_widget, birger_serial_number_displayed=birger_sn)
        camera_sn = self.data['camera_SN']
        self.camera_serial_number = interactive(
            camera_sn_widget, camera_serial_number_displayed=camera_sn)
        lens_sn = self.data['lens_SN']
        self.lens_serial_number = interactive(lens_sn_widget, lens_serial_number_displayed=lens_sn)
        filter_ID = self.data['filter_ID']
        self.filter_ID_code = interactive(filter_ID_widget, filter_ID_code_displayed=filter_ID)
        serial_into_USBhub = self.data['serial_into_USBhub_port']
        self.serial_into_USBhub_port = interactive(
            serial_to_usb_widget, serial_into_USBhub_port_displayed=serial_into_USBhub)
        camera_into_serial = self.data['camera_into_serial_port']
        self.camera_into_serial_port = interactive(
            camera_to_serial_widget, camera_into_serial_port_displayed=camera_into_serial)
        USBhub = self.data['USBhub_SN']
        self.USBhub_SN = interactive(usbhub_sn_widget, USBhub_SN_displayed=USBhub)
        camera_into_USBhub = self.data['camera_into_USBhub_port']
        self.camera_into_USBhub_port = interactive(
            camera_to_usb_widget, camera_into_USBhub_port_displayed=camera_into_USBhub)

        display(self.birger_serial_number)
        display(self.camera_serial_number)
        display(self.lens_serial_number)
        display(self.filter_ID_code)
        display(self.serial_into_USBhub_port)
        display(self.camera_into_serial_port)
        display(self.USBhub_SN)
        display(self.camera_into_USBhub_port)

        self.birger_sn_chosen = self.birger_serial_number.result
        self.camera_sn_chosen = self.camera_serial_number.result
        self.lens_sn_chosen = self.lens_serial_number.result
        self.filter_ID_chosen = self.filter_ID_code.result
        self.serial_to_USBhub_port_chosen = self.serial_into_USBhub_port.result
        self.camera_to_serial_port_chosen = self.camera_into_serial_port.result
        self.USB_hub_SN_chosen = self.USBhub_SN.result
        self.camera_to_USBhub_port_chosen = self.camera_into_USBhub_port.result

        self.camera_type_chosen = self.data['camera_type'][self.camera_sn_chosen]
        self.lens_name_chosen = self.data['lens_name'][self.lens_sn_chosen]
        self.lens_image_stabalisation_chosen = self.data['lens_image_stabalisation'][self.lens_sn_chosen]

        button1 = widgets.Button(description="Add new device set")
        display(button1)
        button1.on_click(self.add_device_widget)

        button = widgets.Button(description="Save File")
        display(button)
        button.on_click(self.save_file)


def birger_sn_widget(birger_serial_number_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        birger_serial_number (str) : the serial number of the birger device as selected from the widget.

    Returns:
        The result of the widget; the chosen focuser serial number

    """
    return birger_serial_number_displayed


def camera_sn_widget(camera_serial_number_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_serial_number (str) : the serial number of the camera device as selected from the widget.

    Returns:
        The result of the widget; the chosen camera serial number

    """
    return camera_serial_number_displayed


def lens_sn_widget(lens_serial_number_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        lens_serial_number (str) : the serial number of the lens device as selected from the widget.

    Returns:
        The result of the widget; the chosen lens serial number

    """
    return lens_serial_number_displayed


def filter_ID_widget(filter_ID_code_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        filter_ID_code (str) : the ID number of the lens as selected from the widget.

    Returns:
        The result of the widget; the chosen filter ID number

    """
    return filter_ID_code_displayed


def serial_to_usb_widget(serial_into_USBhub_port_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        serial_into_USBhub_port (str) : the port number of the USB Hub that the Serial Adaptor is plugged
        into as selected from the widget.

    Returns:
        The result of the widget; the chosen USB port number

    """
    return serial_into_USBhub_port_displayed


def camera_to_serial_widget(camera_into_serial_port_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_into_serial_port (str) : the port number of the Serial Adaptor that the camera is plugged
        into as selected from the widget.

    Returns:
        The result of the widget; the chosen serial port number

    """
    return camera_into_serial_port_displayed


def usbhub_sn_widget(USBhub_SN_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        USBhub_SN (str) : the serial number of the USB Hub as selected from the widget.

    Returns:
        The result of the widget; the chosen USB Hub serial number

    """
    return USBhub_SN_displayed


def camera_to_usb_widget(camera_into_USBhub_port_displayed):
    """Function used to create Jupyter widget.
    It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

    Args:
        camera_into_USBhub_port (str) : the port number of the USB Hub that the camera is plugged into as
        selected from the widget.

    Returns:
        The result of the widget; the chosen USB port number

    """
    return camera_into_USBhub_port_displayed
