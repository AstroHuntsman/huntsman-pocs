import yaml
import os
import datetime
import ipywidgets as widgets
from ipywidgets import interact, interactive, fixed, interact_manual
from IPython.display import display


class writing_config_file(object):
    """

    class description



    """
    def __init__(self):
        self.data = {'serial_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
                'camera_into_serial_port': [1, 2, 3, 4],
                'USBhub_SN': ['OX518EFFE1', 'OXCD12637D'],
                'camera_into_USBhub_port': [0, 1, 2, 3, 4, 5, 6, 7],
                'camera_SN': ['83F011167', '83F011791', '83F011639', '83F010801',
                              '83F010774', '83F011758', '83F010771', '83F011810', 'ML5232816', 'ML1722016'],
                'birger_sn': ['10858', '14287', '14286', '14285', '13281', '13134', '14284', '13208', '14276'],
                'lens_SN': ['3360000099', '3360000063', '3360000087', '2850000067', '3150000110', '5370000054'],
                'filter_ID': ['r2_1', 'r2_2', 'g2_3', 'g2_4', 'r2_5', 'r2_6', 'r2_7', 'g2_8', 'g2_9', 'ha1_10',
                              'ha1_11', 'g2_12', 'ha1_13', 'ha1_14']
                }

        self.birger_sn = self.data['birger_sn']
        self.birger_serial_number = interactive(self.birger_sn_widget, birger_serial_number_displayed=self.birger_sn)
        self.camera_sn = self.data['camera_SN']
        self.camera_serial_number = interactive(self.camera_sn_widget, camera_serial_number_displayed=self.camera_sn)
        self.lens_sn = self.data['lens_SN']
        self.lens_serial_number = interactive(self.lens_sn_widget, lens_serial_number_displayed=self.lens_sn)
        self.filter_ID = self.data['filter_ID']
        self.filter_ID_code = interactive(self.filter_ID_widget, filter_ID_code_displayed=self.filter_ID)
        self.serial_into_USBhub = self.data['serial_into_USBhub_port']
        self.serial_into_USBhub_port = interactive(
            self.serial_to_usb_widget, serial_into_USBhub_port_displayed=self.serial_into_USBhub)
        self.camera_into_serial = self.data['camera_into_serial_port']
        self.camera_into_serial_port = interactive(
            self.camera_to_serial_widget, camera_into_serial_port_displayed=self.camera_into_serial)
        self.USBhub = self.data['USBhub_SN']
        self.USBhub_SN = interactive(self.usbhub_sn_widget, USBhub_SN_displayed=self.USBhub)
        self.camera_into_USBhub = self.data['camera_into_USBhub_port']
        self.camera_into_USBhub_port = interactive(
            self.camera_to_usb_widget, camera_into_USBhub_port_displayed=self.camera_into_USBhub)

        self.birger_sn_chosen = self.birger_serial_number.result
        self.camera_sn_chosen = self.camera_serial_number.result
        self.lens_sn_chosen = self.lens_serial_number.result
        self.filter_ID_chosen = self.filter_ID_code.result
        self.serial_to_USBhub_port_chosen = self.serial_into_USBhub_port.result
        self.camera_to_serial_port_chosen = self.camera_into_serial_port.result
        self.USB_hub_SN_chosen = self.USBhub_SN.result
        self.camera_to_USBhub_port_chosen = self.camera_into_USBhub_port.result

        date_info = datetime.datetime.today()
        datetime_str = date_info.strftime('%Y_%m_%d_%H_%M')
        self.archive_filename = '{}_{}.{}'.format('huntsman', datetime_str, 'yaml')


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
            serial_into_USBhub_port (str) : the port number of the USB Hub that the Serial Adaptor is plugged into as selected from the widget.

        Returns:
            The result of the widget; the chosen USB port number

        """
        return serial_into_USBhub_port_displayed

    def camera_to_serial_widget(camera_into_serial_port_displayed):
        """Function used to create Jupyter widget.
        It takes the parameter chosen from the widget and returns it such that it can be used as a variable.

        Args:
            camera_into_serial_port (str) : the port number of the Serial Adaptor that the camera is plugged into as selected from the widget.

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
            camera_into_USBhub_port (str) : the port number of the USB Hub that the camera is plugged into as selected from the widget.

        Returns:
            The result of the widget; the chosen USB port number

        """
        return camera_into_USBhub_port_displayed


    def choose_local_dir(local_directory='/var/huntsman-pocs/conf_files'):
        """This function enables the user to choose where the .yaml config file will be saved.

        Default path is:
            local_directory='/var/huntsman-pocs/conf_files'

        Args:
            local_directory (optional) : the dir where Huntsman-POCS accesses the config file to be used.

        Returns:
            The path of the local file directory.

        """
        local_direct = local_directory
        return local_direct


    def choose_archive_dir(archive_directory='/var/huntsman-pocs/conf_files/huntsman_archive'):
        """
        This function enables the user to choose where the archive of the .yaml config files will be saved.

        Default path is:
            archive_directory='/var/huntsman-pocs/conf_files/huntsman_archive'

        Args:
            archive_directory (optional) : a dir of archived config files to act as a history/version control.

        Returns:
            The path of the archived files directory.

        """
        archive_direct = archive_directory
        return archive_direct


    def load_previous_data(local_dir, self):
        """
        Function to put the general data from the previous run into a dict.
        It loads the previous .yaml config file and takes all information except the device data.

        Returns:
            The dictionary data_dict of all the general data

        """
        local_dir = self.choose_local_dir
        previous_file = os.path.join(local_dir, 'huntsman.yaml')
        # loading general data from the previous .yaml file used
        with open(previous_file, 'r') as file:
            data_dict = yaml.load(file)

        if 'cameras' in data_dict:
            del data_dict['cameras']

        data_dict.update({'cameras': {'hdr_mode': True, 'auto_detect': False, 'devices': [None]}})

        return data_dict


    def add_device_widget(add_device, self):
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

        additional_device = {'model': camera_dict[self.camera_sn_chosen],
                             'port': self.camera_sn_chosen,
                             'filter_type': self.filter_ID_chosen,
                             'focuser': {'model': 'birger',
                                         'port': self.birger_sn_chosen

                                         },
                             'lens': {'model': 'canon',
                                      'port': self.lens_sn_chosen,
                                      'name': lens_name_dict[self.lens_sn_chosen],
                                      'image_stabalisataion': lens_image_stabalisation[self.lens_sn_chosen]},
                             'USB_hub_serial_number': self.USB_hub_SN_chosen,
                             'camera_into_serial_adaptor_port': self.camera_to_serial_port_chosen,
                             'serial_adaptor_into_USBhub_port': self.serial_to_USBhub_port_chosen,
                             'camera_into_USBhub_port': self.camera_to_USBhub_port_chosen
                             }

        data_list = self.load_previous_data(self.choose_local_dir)

        if data_list['cameras']['devices'] == [None]:
            data_list['cameras']['devices'] = [additional_device]
        else:
            data_list['cameras']['devices'].append(additional_device)


    def save_file_widget(save_file, self):
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

        strOutFile1 = os.path.join(self.choose_local_dir, 'huntsman.yaml')
        objFile1 = open(strOutFile1, "w")
        yaml.dump(self.data_list, objFile1, default_flow_style=False, indent=4)
        objFile1.close()

        strOutFile = os.path.join(self.choose_archive_dir, self.archive_filename)
        objFile = open(strOutFile, "w")
        yaml.dump(self.data_list, objFile, default_flow_style=False, indent=4)
        objFile.close()


    def create_yaml_file(self):
        """This function runs all the code to generate the .yaml config files for the Huntsman-POCS system.
        It displays the Jupyter widgets which the user can interact with to write and save the config files.

        Files are saved in two locations, one for the local file that POCS will access, and the other is an archive of all previous config files which acts as a version control.
        By default, these locations are: (but can be changed using the choose_dir() function)
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

        display(self.birger_serial_number)
        display(self.camera_serial_number)
        display(self.lens_serial_number)
        display(self.filter_ID_code)
        display(self.serial_into_USBhub_port)
        display(self.camera_into_serial_port)
        display(self.USBhub_SN)
        display(self.camera_into_USBhub_port)

        button1 = widgets.Button(description="Add new device set")
        display(button1)
        button1.on_click(self.add_device_widget)

        button = widgets.Button(description="Save File")
        display(button)
        button.on_click(self.save_file_widget)
