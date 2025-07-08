import ctypes
import enum

from panoptes.pocs.camera.libasi import ASIDriver

# from panoptes.pocs.camera.libasi import ControlType as BaseControlType


# class ControlType(BaseControlType):
#     """Extended control types for Huntsman."""

#     ASI_FAN_ADJUST = enum.auto()
#     ASI_PWRLED_BRIGNT = enum.auto()
#     ASI_GPS_SUPPORT = enum.auto()
#     ASI_GPS_START_LINE = enum.auto()
#     ASI_GPS_END_LINE = enum.auto()
#     ASI_ROLLING_INTERVAL = enum.auto()  # microsecond


class HuntsmanASIDriver(ASIDriver):
    """Huntsman-specific implementation of the ASI Camera driver."""

    def get_dropped_frames(self, camera_ID):
        """Get the number of dropped frames during video capture."""
        n_dropped_frames = ctypes.c_int()
        self._call_function(
            'ASIGetDroppedFrames', camera_ID, ctypes.byref(n_dropped_frames)
        )
        self.logger.debug(
            "Camera {} has dropped {} frames.".format(camera_ID, n_dropped_frames)
        )
        return n_dropped_frames
