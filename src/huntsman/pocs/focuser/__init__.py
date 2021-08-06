""" Base Huntsman override class. """
import os
import numpy as np

from panoptes.utils import error
from panoptes.utils.time import current_time

from panoptes.pocs.focuser.focuser import AbstractFocuser
from panoptes.pocs.utils.plotting import make_autofocus_plot

from huntsman.pocs.utils.focus import create_autofocus_sequence

__all__ = ("HuntsmanFocuser",)


class HuntsmanFocuser(AbstractFocuser):
    """ Base class for Huntsman overrides to focuser. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        position_min = initial_position - focus_range[idx] / 2
        position_max = initial_position + focus_range[idx] / 2

        # Apply focuser movement boundaries
        if self.max_position is not None:
            position_max = min(position_max, self.max_position)
        if self.min_position is not None:
            position_min = max(position_min, self.min_position)

        # Make autofocus sequence
        sequence = create_autofocus_sequence(
            position_min=position_min, position_max=position_max, position_step=position_step,
            bit_depth=self.camera.bit_depth, config=self.config, logger=self.logger, **kwargs)

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

        # Get the best position
        best_position = sequence.best_actual_position
        self.logger.info(f"Best focus position for {self}: {best_position}")

        # Move to the best position
        final_position = self.move_to(best_position)
        self.logger.debug(f"Moved to best position: {final_position}")

        if make_plots:
            focus_type = "coarse" if coarse else "fine"
            plot_filename = os.path.join(imagedir, f'{focus_type}-focus-{self.camera.uid}.png')
            plot_title = f'{self} {focus_type} focus at {start_time}'

            metrics = sequence.metrics
            focus_positions = sequence.actual_positions
            merit_function = sequence.merit_function_name

            initial_idx = np.argmin(abs(focus_positions - initial_position))
            initial_cutout = sequence.images[initial_idx]

            final_idx = np.argmin(abs(focus_positions - best_position))
            final_cutout = sequence.images[final_idx]

            self.logger.info(f"Writing focus plot for {self} to {plot_filename}.")
            make_autofocus_plot(plot_filename, initial_cutout, final_cutout, initial_position,
                                best_position, focus_positions, metrics, merit_function,
                                plot_title=plot_title)

        return initial_position, best_position
