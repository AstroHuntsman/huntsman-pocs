from astropy import units as u


class FakeASIDriver:
    def __init__(self, library_path=None):
        self.version = '0.1.0'
        self._cameras = {
            '123456789': {
                'camera_ID': 0,
                'name': 'ZWO ASI1600MM Pro',
                'has_cooler': True,
                'is_color_camera': False,
                'bayer_pattern': None,
                'bit_depth': 12,
                'pixel_size': 3.8 * u.um,
                'supported_video_format': ['RAW8', 'RAW16'],
                'e_per_adu': 0.5,
            }
        }
        self._control_caps = {
            0: {
                'GAIN': {
                    'name': 'Gain',
                    'is_writable': True,
                    'max_value': 100,
                    'min_value': 0,
                    'is_auto_supported': True,
                },
                'EXPOSURE': {
                    'name': 'Exposure',
                    'is_writable': True,
                    'max_value': 1000 * u.s,
                    'min_value': 0 * u.s,
                    'is_auto_supported': True,
                },
                'TEMPERATURE': {
                    'name': 'Temperature',
                    'is_writable': False,
                },
                'TARGET_TEMP': {
                    'name': 'Target Temperature',
                    'is_writable': True,
                    'max_value': 30,
                    'min_value': -20,
                    'is_auto_supported': False,
                },
                'COOLER_POWER_PERC': {
                    'name': 'Cooler Power',
                    'is_writable': False,
                },
                'COOLER_ON': {
                    'name': 'Cooler On',
                    'is_writable': True,
                    'max_value': 1,
                    'min_value': 0,
                    'is_auto_supported': False,
                },
            }
        }
        self._control_values = {
            0: {
                'GAIN': 0,
                'EXPOSURE': 0.1,
                'TEMPERATURE': 10 * u.Celsius,
                'TARGET_TEMP': 10 * u.Celsius,
                'COOLER_ON': False,
                'COOLER_POWER_PERC': 0 * u.percent,
            }
        }
        self._roi_format = {
            0: {
                'width': 1024,
                'height': 768,
                'image_type': 'RAW16',
            }
        }
        self._exposure_status = {0: 'IDLE'}

    def get_devices(self):
        return {sn: f'/dev/fake-asi-{i}' for i, sn in enumerate(self._cameras.keys())}

    def get_camera_property(self, address):
        # address is /dev/fake-asi-0
        # Invert the get_devices logic to find the serial number
        for sn, addr in self.get_devices().items():
            if addr == address:
                return self._cameras[sn]
        raise KeyError(address)

    def open_camera(self, camera_ID):
        pass

    def init_camera(self, camera_ID):
        pass

    def get_control_caps(self, camera_ID):
        return self._control_caps[camera_ID]

    def disable_dark_subtract(self, camera_ID):
        pass

    def close_camera(self, camera_ID):
        pass

    def get_roi_format(self, camera_ID):
        return self._roi_format[camera_ID]

    def set_roi_format(self, camera_ID, width, height, image_type):
        self._roi_format[camera_ID]['width'] = width
        self._roi_format[camera_ID]['height'] = height
        self._roi_format[camera_ID]['image_type'] = image_type

    def get_control_value(self, camera_ID, control_type):
        return self._control_values[camera_ID][control_type], True

    def set_control_value(self, camera_ID, control_type, value):
        if control_type == 'EXPOSURE' and isinstance(value, u.Quantity):
            value = value.to_value(u.s)
        self._control_values[camera_ID][control_type] = value
        return True

    def get_exposure_status(self, camera_ID):
        return self._exposure_status[camera_ID]

    def start_video_capture(self, camera_ID):
        self._exposure_status[camera_ID] = 'WORKING'

    def stop_video_capture(self, camera_ID):
        self._exposure_status[camera_ID] = 'IDLE'

    def get_video_data(self, camera_ID, width, height, image_type, timeout):
        import numpy as np
        import time
        # Simulate exposure time
        time.sleep(self._control_values[camera_ID]['EXPOSURE'])
        return np.zeros((height, width), dtype=np.uint16)

    def start_exposure(self, camera_ID, is_dark=False):
        self._exposure_status[camera_ID] = 'WORKING'
        # In a real scenario, this would be asynchronous.
        # For the fake driver, we can simulate the exposure being done after some time.
        # For now, just set it to success.
        self._exposure_status[camera_ID] = 'SUCCESS'

    def get_exposure_data(self, camera_ID, width, height, image_type):
        import numpy as np
        self._exposure_status[camera_ID] = 'IDLE'
        return np.zeros((height, width), dtype=np.uint16)

    def get_product_ids(self):
        return [0x0001]  # Fake product ID
