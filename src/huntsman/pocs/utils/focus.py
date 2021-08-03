from functools import partial

import numpy as np
from scipy.ndimage import binary_dilation

from panoptes.utils.images import mask_saturated
from panoptes.utils.library import load_module
from panoptes.utils.config.client import get_config

from panoptes.pocs.base import PanBase

from huntsman.pocs.utils.logger import get_logger


DEFAULT_METRIC = "panoptes.utils.images.focus.vollath_F4"


def fourier_focus_metric(image, crop=1):
    """ Focus metric based on gradient of fourier power spectrum.
    When very defocused, most of the power will be in either white noise or concentrated at low
    spatial frequencies. In this case, a linear fit to the full spectrum will have a shallow
    gradient. When there is significant power at higher spatial frequencies (i.e. as the focus
    improves), the gradient will increase. It is therefore a suitable focus metric.
    Args:
        image (np.array): The image array.
        crop (float, optional): The number of low spatial frequency pixels in the FFT image to
            exclude from the fit. The default is 1, in order to remove the DC component from the
            FFT. This is typically very large compared to the rest of the spectrum because of the
            background level.
    Returns:
        float ()
    """
    from scipy import fftpack
    from scipy.optimize import curve_fit

    size = image.shape[1]
    halfsize = size / 2

    # Calculate FT of image
    fft = np.abs(fftpack.fft2(image))

    yy, xx = np.meshgrid(np.arange(size), np.arange(size))
    rr = np.sqrt((xx - halfsize) ** 2 + (yy - halfsize) ** 2)

    # Get 1D data to fit
    x = rr.reshape(-1)
    y = fft.reshape(-1)
    if crop:
        cond = rr < rr.max() - crop
        x = x[cond]
        y = y[cond]

    # Fit line to 1D power spectrum
    try:
        popt = curve_fit(lambda x, m, c: m * x + c, xdata=x, ydata=y)[0]
        result = popt[0]
    except Exception:
        result = 0

    # Use gradient of line as metric
    return result


def create_autofocus_sequence(config=None, logger=None, *args, **kwargs):
    """ Create an AutofocusSequence from config.
    Args:
        config (dict, optional): The config dict. Use default config if None.
        logger (logger, optional): The logger. Use default logger if None.
        *args, **kwargs: Parsed to AutofocusSequence init function. Overrides default config values.
    Returns:
        AutofocusSequence: The configured autofocus sequence.
    """
    if config is None:
        config = get_config()

    if logger is None:
        logger = get_logger()

    sequence_kwargs = config.get("AutofocusSequence", {})
    sequence_kwargs.update(kwargs)

    logger.debug(f"Creating AutofocusSequence with kwargs: {sequence_kwargs}")

    return AutofocusSequence(config=config, logger=logger, *args, **sequence_kwargs)


class AutofocusSequence(PanBase):
    """ The purpose of the AutofocusSequence is to facilitate autofocusing that is robust against
    failed exposures. This is achieved through the public 'update' method in combination with
    the 'is_finished' property.
    """

    def __init__(self, position_min, position_max, position_step, bit_depth,
                 hot_pixel_threshold=0.3, extra_focus_steps=5, mask_dilations=15,
                 merit_function_name=DEFAULT_METRIC, merit_function_kwargs=None,
                 image_dtype=np.float32, saturation_mask_threshold=0.9, apply_mask=True,
                 **kwargs):
        """
        Args:
            position_min (int): The minimal focus position.
            position_max (int): The maximal focus position.
            position_step (int): The step in focus position.
            bit_depth (astropy.units.Quantity): The bit depth of the images.
            saturation_mask_threshold (float): The staturation masking threshold to apply to focus
                images. Default: 0.9.
            hot_pixel_threshold (float, optional): The staturation masking threshold to eliminate
                hot pixels from initial dark frame. Default: 0.3.
            extra_focus_steps (int, optional): The number of extra focus steps to be measured if
                the best focus is at the edge of the initial range. Default 2.
            mask_dilations (int, optional): The number of mask dilations to perform. Default 10.
            merit_function_name (str, optional): The name of the focus merit function.
                Default 'vollath_F4'.
            merit_function_kwargs (dict, optional): Extra kwargs for the merit function.
            image_dtype (str or Type, optional): The image data type. Default np.float32.
            **kwargs parsed to PanBase.
        """
        super().__init__(**kwargs)

        self._position_min = int(position_min)
        self._position_max = int(position_max)
        self._position_step = int(position_step)
        self._bit_depth = bit_depth
        self._saturation_mask_threshold = float(saturation_mask_threshold)
        self._hot_pixel_threshold = float(hot_pixel_threshold)
        self._extra_focus_steps = int(extra_focus_steps)
        self._mask_dilations = int(mask_dilations)
        self._image_dtype = image_dtype
        self._apply_mask = bool(apply_mask)

        # Create the merit function
        merit_function_kwargs = {} if merit_function_kwargs is None else merit_function_kwargs
        merit_function = load_module(merit_function_name)
        self.merit_function_name = merit_function_name
        self._merit_function = partial(merit_function, **merit_function_kwargs)

        # Define initial values
        self._exposure_idx = 0
        self._best_index = None
        self._dark_image = None
        self._dark_mask = None
        self._image_shape = None
        self._mask = None
        self._metrics = None

        # Setup focus positions
        self._positions = np.arange(self._position_min, self._position_max + self._position_step,
                                    self._position_step)
        self._positions_actual = []
        self.images = []

    # Properties

    @property
    def exposure_idx(self):
        """ The number of completed exposures.
        Returns:
            int: The exposure index.
        """
        return self._exposure_idx

    @property
    def n_positions(self):
        """ The number of focus positions in the sequence. This is a property so that it will
        automatically update itself if the focus range gets expanded.
        Returns:
            int: The number of focus positions.
        """
        return self._positions.size

    @property
    def is_finished(self):
        """ Check if the sequence is finished yet.
        Returns:
            bool: True if the sequence is finished, else False.
        """
        return self._best_index is not None

    @property
    def status(self):
        """ Return the status of the exposure sequence.
        Returns:
            dict: The sequence status dictionary.
        """
        return {"is_finished": self.is_finished,
                "completed_positions": self.exposure_idx,
                "total_positions": self.n_positions}

    @property
    def dark_image(self):
        """ Return the dark image.
        Returns:
            np.array: The dark image.
        """
        return self._dark_image

    @dark_image.setter
    def dark_image(self, image):
        """ Set the dark image and update the dark mask.
        Args:
            image (np.array): The dark image array.
        """
        self._dark_image = image.astype(self._image_dtype)
        self._dark_mask = self._mask_saturated(self._dark_image,
                                               threshold=self._hot_pixel_threshold)

    @property
    def positions(self):
        """ Return the actual focus positions (i.e. not the requested ones).
        This can only be obtained after the sequence has finished.
        Returns:
            np.array: The 1D array of actual focus positions.
        """
        if not self.is_finished:
            raise AttributeError("The focus sequence is not complete.")
        return np.array(self._positions_actual)

    @property
    def best_position(self):
        """ Get the best focus position.
        This can only be obtained after the sequence has finished.
        Returns:
            int: The best focus position.
        """
        if not self.is_finished:
            raise AttributeError("The focus sequence is not complete.")
        return self.positions[self._best_index]

    @property
    def metrics(self):
        """ Return the focus metrics for each position.
        This can only be obtained after the sequence has finished.
        Returns:
            np.array: 1D array of focus metrics.
        """
        if not self.is_finished:
            raise AttributeError("The focus sequence is not complete.")
        return self._metrics

    # Public methods

    def update(self, image, position):
        """ Update the autofocus sequence with a new image.
        Args:
            image (np.array): The image array.
            position (int): The actual focuser position of the image.
        """
        self.logger.debug(f"Adding image to focus sequence at position={position}.")

        if self.is_finished:
            raise RuntimeError("Cannot update completed autofocus sequence.")

        if self._mask is None:
            self._mask = np.zeros(shape=image.shape, dtype="bool")

        self._positions_actual.append(position)
        self.images.append(image.astype(self._image_dtype))

        # Subtract dark image
        if self.dark_image is not None:
            self.images[-1] -= self.dark_image
        else:
            self.logger.warning("Updating autofocus sequence but dark image not set.")

        # Update the mask
        self._mask = np.logical_or(self._mask, self._mask_saturated(self.images[self.exposure_idx]))

        # Update the exposure index
        self._exposure_idx += 1
        if self.exposure_idx == self.n_positions:

            # Calculate metrics
            metrics = self._calculate_metrics()
            best_index = np.nanargmax(metrics)

            # Check if the sequence is finished
            best_in_valid_range = best_index not in (0, self.n_positions - 1)
            extra_focus_steps_required = self._extra_focus_steps > 0
            is_finished = best_in_valid_range or not extra_focus_steps_required

            # Check if the sequence is finished
            if is_finished:
                self._best_index = best_index
                self._metrics = metrics
                return

            self.logger.warning(f"Best focus position outside range for {self}.")

            # Check if we should expand the focusing range
            if extra_focus_steps_required:
                self.logger.warning(f"Expanding focus range for {self}.")
                self._expand_focus_range(best_index)

    def get_next_position(self):
        """ Return the next focus position in the sequence.
        Returns:
            int: The next focus position.
        """
        return self._positions[self.exposure_idx]

    # Private methods

    def _mask_saturated(self, image, threshold=None):
        """ Mask the saturated pixels in an image.
        Args:
            image (np.array): The image to mask.
            threshold (float): The mask threshold, between 0 and 1. Defaults to
                self._saturation_mask_threshold.
        Returns:
            np.array: The boolean mask, where values of True are masked.
        """
        if threshold is None:
            threshold = self._saturation_mask_threshold
        return mask_saturated(image, bit_depth=self._bit_depth, threshold=threshold).mask

    def _calculate_metrics(self):
        """ Calculate the focus metric for all the focus positions.
        Returns:
            np.array: A 1D array of the focus metrics.
        """
        mask = binary_dilation(self._mask, iterations=self._mask_dilations)

        # Update the mask with the dark mask
        # NOTE: The dark mask should not be dilated since it should be masking hot pixels
        if self._dark_image is not None:
            mask = np.logical_or(mask, self._dark_mask)

        if self._apply_mask:
            self.logger.debug(f"Autofocus masked fraction: {mask.mean():.2f}")

        metrics = []
        for image in self.images:
            im = np.ma.array(image, mask=mask) if self._apply_mask else image
            metrics.append(self._merit_function(im))

        return np.array(metrics)

    def _expand_focus_range(self, best_index):
        """ Expand the focusing range by a fixed number of steps.
        Args:
            best_index (int): The index of the best focus position.
        """
        # Get positions of expanded range
        if best_index == 0:
            min_position = self._position_min - self._extra_focus_steps * \
                self._position_step
            max_position = self._position_min
        else:
            min_position = self._position_max + self._position_step
            max_position = self._position_max + (self._extra_focus_steps + 1) * \
                self._position_step

        # Update positions
        extra_positions = np.arange(min_position, max_position, self._position_step)
        self._positions = np.hstack([self._positions, extra_positions])

        # Setting this to zero stops the positions being expanded again
        self._extra_focus_steps = 0
