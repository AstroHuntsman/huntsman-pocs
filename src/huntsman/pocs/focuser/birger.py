""" Modified focuser to reconnect serial port on command error. """
import os
import numpy as np

from panoptes.utils import error
from panoptes.utils.time import current_time

from panoptes.pocs.focuser.birger import Focuser as BirgerFocuser
from panoptes.pocs.utils.plotting import make_autofocus_plot

from huntsman.pocs.utils.focus import AutofocusSequence


class Focuser(BirgerFocuser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def reconnect(self):
        """ Close and open serial port and reconnect to focuser. """
        self.logger.debug(f"Attempting to reconnect to {self}.")
        self.__del__()
        self.connect(port=self.port)

    def autofocus(self, *args, **kwargs):
        """ Override method to move FWs. """

        filter_name = kwargs.pop("filter_name", None)

        # Move filterwheel to the correct position
        if self.camera is not None:
            if self.camera.has_filterwheel:

                if filter_name is None:
                    # NOTE: The camera will move the FW to the last light position automatically
                    self.logger.warning(f"Filter name not provided for autofocus on {self}. Using"
                                        " last light position.")
                else:
                    self.logger.info(f"Moving filterwheel to {filter_name} for autofocusing on"
                                     f" {self}.")
                    self.camera.filterwheel.move_to(filter_name, blocking=True)

            elif filter_name is None:
                self.logger.warning(f"Filter {filter_name} requiested for autofocus but"
                                    f" {self.camera} has no filterwheel.")

        return super().autofocus(*args, **kwargs)

    def _send_command(self, *args, **kwargs):
        """ Try command, attempt to reconnect on error and send command again. """
        try:
            return super()._send_command(*args, **kwargs)
        except error.PanError as err:
            self.logger.warning(f"Focuser command failed with exception: {err!r}. Retrying after"
                                " reconnect.")
            self.reconnect()
            return super()._send_command(*args, **kwargs)

    def _autofocus(self, *args, **kwargs):
        focus_event = kwargs.pop("focus_event")
        try:
            return self._run_autofocus(*args, **kwargs)
        finally:
            if focus_event is not None:
                focus_event.set()

    def _run_autofocus(self, seconds, focus_range, focus_step, cutout_size, keep_files=False,
                       take_dark=True, coarse=False, make_plots=False, max_exposure_retries=3,
                       **kwargs):
        """
        Focuses the camera using the specified merit function. Optionally performs
        a coarse focus to find the approximate position of infinity focus, which
        should be followed by a fine focus before observing.
        Args:
            seconds (scalar, optional): Exposure time for focus exposures, if not
                specified will use value from config.
            focus_range (2-tuple, optional): Coarse & fine focus sweep range, in
                encoder units. Specify to override values from config.
            focus_step (2-tuple, optional): Coarse & fine focus sweep steps, in
                encoder units. Specify to override values from config.
            cutout_size (int, optional): Size of square central region of image
                to use, default 500 x 500 pixels.
            keep_files (bool, optional): If True will keep all images taken
                during focusing. If False (default) will delete all except the
                first and last images from each focus run.
            take_dark (bool, optional): If True will attempt to take a dark frame
                before the focus run, and use it for dark subtraction and hot
                pixel masking, default True.
            coarse (bool, optional): Whether to perform a coarse focus, otherwise will perform
                a fine focus. Default False.
            make_plots (bool, optional): Whether to write focus plots to images folder. If not
                given will fall back on value of `autofocus_make_plots` set on initialisation,
                and if it wasn't set then will default to False.
            blocking (bool, optional): Whether to block until autofocus complete, default False.
        """
        start_time = start_time = current_time(flatten=True)
        imagedir = os.path.join(self.camera.get_config('directories.images'), 'focus',
                                self.camera.uid, start_time)
        initial_position = self.position

        # Get focus range
        idx = 1 if coarse else 0
        position_step = focus_step[idx]
        position_min = max(self.min_position, initial_position - focus_range[idx] / 2)
        position_max = min(self.max_position, initial_position + focus_range[idx] / 2)

        # Make sequence object
        sequence = AutofocusSequence(position_min=position_min, position_max=position_max,
                                     position_step=position_step, bit_depth=self.camera.bit_depth,
                                     **kwargs)
        # Add a dark exposure
        if take_dark:
            self.logger.info(f"Taking dark frame before autofocus on {self}.")
            filename = os.path.join(imagedir, f"dark.{self.camera.file_extension}")
            cutout = self.camera.get_cutout(seconds, filename, cutout_size, keep_file=keep_files,
                                            dark=True)
            sequence.dark_image = cutout

        # Take the focusing exposures
        exposure_retries = 0
        while not sequence.is_finished:
            self.logger.info(f"Autofocus status on {self}: {sequence.status}")

            new_position = sequence.get_next_position()

            basename = f"{new_position}-{sequence.exposure_idx:02d}.{self.camera.file_extension}"
            filename = os.path.join(imagedir, basename)

            # Move the focuser
            self.move_to(new_position)

            # Get the exposure cutout
            try:
                cutout = self.camera.get_cutout(seconds, filename, cutout_size,
                                                keep_file=keep_files)
                exposure_retries = 0  # Reset exposure retries
            except error.PanError as err:
                self.logger.warning(f"Exception encountered in get_cutout on {self}: {err!r}")

                # Abort the sequence if max exposure retries is reached
                exposure_retries += 1
                if exposure_retries >= max_exposure_retries:
                    raise error.PanError(f"Max exposure retries reached during autofocus on"
                                         f" {self}.")
                self.logger.warning("Continuing with autofocus sequence after exposure error on"
                                    f" {self}.")
                continue

            # Update the sequence
            sequence.update(cutout, position=self.position)

        # Get the best position and move to it
        best_position = sequence.best_position
        best_position_actual = self.move_to(best_position)
        self.logger.info(f"Best focus position for {self}: {best_position}")

        if make_plots:
            focus_type = "coarse" if coarse else "fine"
            plot_filename = os.path.join(imagedir, f'{focus_type}-focus-{self.camera.uid}.png')
            plot_title = f'{self} {focus_type} focus at {start_time}'

            metrics = sequence.metrics
            focus_positions = sequence.positions
            merit_function = sequence.merit_function_name

            initial_idx = np.argmin(abs(focus_positions - initial_position))
            initial_cutout = sequence.images[initial_idx]

            final_idx = np.argmin(abs(focus_positions - best_position))
            final_cutout = sequence.images[final_idx]

            self.logger.info(f"Writing focus plot for {self} to {plot_filename}.")
            make_autofocus_plot(plot_filename, initial_cutout, final_cutout, initial_position,
                                best_position_actual, focus_positions, metrics, merit_function,
                                plot_title=plot_title)

        return initial_position, best_position
