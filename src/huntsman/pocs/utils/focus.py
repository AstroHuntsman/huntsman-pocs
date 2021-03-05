from functools import partial
import numpy as np

from panoptes.pocs.base import PanBase
from panoptes.utils.images import mask_saturated

IMAGE_DTYPE = np.float32


class AutofocusSequence(PanBase):

    def __init__(self, position_min, position_max, position_step, merit_function, bit_depth,
                 mask_threshold=0.3, extra_focus_steps=2, merit_function_kwargs=None, do_fit=False,
                 **kwargs):
        """
        """
        super().__init__(**kwargs)

        self._position_min = int(position_min)
        self._position_max = int(position_max)
        self._position_step = int(position_step)
        self._bit_depth = int(bit_depth)
        self._mask_threshold = float(mask_threshold)
        self._extra_focus_steps = int(extra_focus_steps)
        self._do_fit = bool(do_fit)

        if merit_function_kwargs is not None:
            merit_function = partial(merit_function, **merit_function_kwargs)
        self._merit_function = merit_function

        self._exposure_index = 0
        self._best_index = None
        self._dark_image = None
        self._image_shape = None
        self._images = None
        self._mask = None
        self._metrics = None
        self._best_fit_position = None

        # Setup focus positions
        self._positions = np.arange(self._position_min, self._position_max + self._position_step,
                                    self._position_step)
        self._positions_actual = []
        self.n_positions = self._positions.size

    @property
    def n_positions(self):
        return self._positions.size

    @property
    def is_finised(self):
        """
        """
        return self._best_index is not None

    @property
    def status(self):
        return {"is_finished": self.is_finished,
                "completed_exposures": self._exposure_index,
                "n_positions": self.n_positions}

    @property
    def best_position(self):
        """
        """
        if not self.is_finished:
            raise RuntimeError("The focus sequence is not complete.")
        if self._do_fit:
            return self._best_fit_position
        return self._positions[self._best_index]

    @property
    def dark_image(self):
        """
        """
        return self._dark_image

    @dark_image.setter
    def dark_image(self, image):
        """
        """
        if self._image_shape is None:
            self._initialise_images(image.shape)

        self._dark_image = image.astype(IMAGE_DTYPE)
        self._mask = np.logical_or(self._mask, self._mask_saturated(self._dark_image))

    def update(self, image, focus_position):
        """
        """
        if self._image_shape is None:
            self._initialise_images(image.shape)

        self._positions_actual.append(int(focus_position))

        # Store the image
        self._images[self._exposure_index, :, :] = image
        if self.dark_image is not None:
            self._images[self._exposure_index] -= self.dark_image

        # Update the mask
        self._mask = np.logical_or(self._mask,
                                   self._mask_saturated(self._images[self._exposure_index]))

        # Update the exposure index
        self._exposure_index += 1
        if self._exposure_index == self.n_positions:

            # Calculate metrics
            metrics = np.array([self._merit_function(im) for im in self.images])
            best_index = np.argmax(metrics)

            # Check if the sequence is finished
            if best_index not in (0, self.n_positions - 1):
                self._best_index = best_index
                self._metrics = metrics

                # Do the fit if required
                if self._do_fit:
                    self._fit()
                return

            self.logger.warning(f"Best focus position outside range for {self}.")

            # Check if we should expand the focusing range
            if self._extra_focus_steps > 0:
                self.logger.warning(f"Expanding focus range for {self}.")

                # Update positions
                if best_index == 0:
                    min_position = self._min_position - self._extra_focus_steps * \
                        self._position_step
                    max_position = self._min_position
                else:
                    min_position = self._max_position + self._position_step
                    max_position = self._max_position + (self._extra_focus_steps + 1) * \
                        self._position_step

                extra_positions = np.arange(min_position, max_position, self._position_step)
                self.positions = np.vstack([self._positions, extra_positions])

                # Setting this to zero stops the positions being expanded again
                self._extra_focus_steps = 0

    def get_next_position(self):
        """
        """
        return self._positions[self._exposure_index]

    def _mask_saturated(self, image):
        """
        """
        return mask_saturated(image, threshold=self._mask_threshold, bit_depth=self._bit_depth)

    def _initialise_images(self, shape):
        """
        """
        self._image_shape = shape
        self._mask = np.zeros(shape, dtype="bool")
        self._images = np.zeros((self.n_positions, *shape), dtype=IMAGE_DTYPE)

    def _fit(self):
        """ Fit data around the maximum value to determine best focus position. """
        raise NotImplementedError

    def make_plot(self, filename, title=None, **kwargs):
        """ """
        raise NotImplementedError
