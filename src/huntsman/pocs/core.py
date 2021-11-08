import time
from collections import deque

from astropy import units as u
from panoptes.utils.utils import get_quantity_value
from panoptes.utils.time import current_time

from panoptes.pocs.core import POCS


class HuntsmanPOCS(POCS):
    """ Minimal overrides to the POCS class to control Huntsman state machine behaviour """

    def __init__(self, *args, **kwargs):
        self._dome_open_states = []
        super().__init__(*args, **kwargs)

        # Record the latest times of the dark_state here
        max_dark_per_interval = self.get_config("calibs.dark.max_blocks_per_interval", 3)
        self._dark_state_times = deque(maxlen=max_dark_per_interval)

        dark_interval = self.get_config("calibs.dark.dark_interval_hours", 6)
        self._dark_interval = get_quantity_value(dark_interval, u.hour) * u.hour

        # Hack solution to provide POCS.is_safe functionality to observatory
        self.logger.debug(f"Setting _is_safe for {self.observatory}.")
        self.observatory._is_safe = self.is_safe

    # Properties

    @property
    def should_take_darks(self):
        """ Check if we should enter the darks state.
        Returns:
            bool: True if we should enter the darks state, else False.
        """
        veto = False

        # We do not want to take darks when it is dark and the weather is safe
        if self.is_weather_safe() and self.is_dark(horizon="twilight_max"):
            self.logger.debug("Vetoing darks because we can observe.")
            veto = True

        # We do not want to take darks if we have already taken too many recently
        elif len(self._dark_state_times) == self._dark_state_times.maxlen:
            timediff = current_time() - self._dark_state_times[0]
            if timediff < self._dark_interval:
                self.logger.debug("Vetoing darks because we have taken too many recently.")
                veto = True

        # We do not want to take darks if the dome is open
        # If we are in this position, log a warning as it should not happen normally
        elif self.observatory.dome.is_open:
            self.logger.debug("Vetoing darks because dome is open.")
            self.logger.warning("Tried to enter darks state while dome is open.")
            veto = True

        return not veto

    # Public methods

    def run(self, initial_next_state='starting', initial_focus=True, *args, **kwargs):
        """ Override the default initial_next_state parameter from "ready" to "starting".
        This allows us to call pocs.run() as normal, without needing to specify the initial next
        state explicitly.
        Args:
            initial_next_state (str, optional): The first state the machine should move to from
                the `sleeping` state, default `starting`.
            skip_coarse_focus (bool, optional): If True, will skip the initial coarse focus.
                Default False.
            *args, **kwargs: Parsed to POCS.run.
        """
        # Override last coarse focus time if not doing initial coarse focus.
        if initial_focus is False:
            self.observatory.last_coarse_focus_time = current_time()
        return super().run(initial_next_state=initial_next_state, *args, **kwargs)

    def stop_states(self):
        """ Park then stop states. """
        try:
            self.logger.info("Parking the telescope before stopping states.")
            self.park()
            self.set_park()
        except Exception as err:
            self.logger.error(f"Unable to park after stopping states: {err!r}")
        super().stop_states()

    def before_state(self, event_data):
        """ Called before each state.
        Args:
            event_data(transitions.EventData):  Contains information about the event
        """
        if self.next_state in self._dome_open_states:
            self.say(f"Opening the dome before entering the {self.next_state} state.")
            self.observatory.open_dome()
        self.say(f"Entering {self.next_state} state from the {self.state} state.")

    def after_state(self, event_data):
        """ Called after each state.
        Args:
            event_data(transitions.EventData):  Contains information about the event
        """
        self.say(f"Finished with the {self.state} state. The next state is {self.next_state}.")

    def is_weather_safe(self, **kwargs):
        """Determines whether current weather conditions are safe or not.
        Args:
            stale (int, optional): Number of seconds before record is stale, defaults to 180
        Returns:
            bool: Conditions are safe (True) or unsafe (False)
        """
        if self._in_simulator('weather'):
            return True
        # if not in simulator mode, determine safety from huntsman weather data
        is_safe_list = [super().is_weather_safe(**kwargs)]

        # check alternate sources
        alt_weather_config = self.get_config("alt_weather_sources", default=None)
        sources_to_check = [s for s in alt_weather_config.keys()
                            if alt_weather_config[s]['use'] is True]

        for source in sources_to_check:
            is_safe_list.append(self.is_alt_weather_safe(source))

        return all(is_safe_list)

    def is_alt_weather_safe(self, source, stale=180):
        """Checks alternative weather source readings to determine safety.
        Args:
            source (str): Name of alternate weather source collection to examine.
            stale (int, optional): Number of seconds before record is stale, defaults to 180
        Returns:
            bool: Conditions are safe (True) or unsafe (False)
        """
        self.logger.debug(f"Checking {source} safety")

        # Get current weather readings from database
        is_safe = False
        try:
            record = self.db.get_current(source)
            if record is None:
                return False

            is_safe = record['data'].get('safe', False)

            timestamp = record['date'].replace(tzinfo=None)  # current_time is timezone naive
            age = (current_time().datetime - timestamp).total_seconds()

            self.logger.debug(
                f"Weather Safety: {is_safe} [{age:.0f} sec old - {timestamp:%Y-%m-%d %H:%M:%S}]")

        except Exception as e:  # pragma: no cover
            self.logger.error(f"No {source} record in database: {e!r}")
        else:
            if age >= stale:
                self.logger.warning(f"{source} record looks stale, marking unsafe.")
                is_safe = False

        return is_safe

    def wait_for_twilight(self):
        """ Wait for twilight.
        Twilight is currently defined as when the Sun is between the flat and focus horizons.
        Returns:
            bool: True if we safely waited for twilight, False if it is not safe to continue.
        """
        self.logger.info('Waiting for twilight.')

        delay = self.get_config("wait_delay", 60)

        while not self.observatory.is_twilight:
            if self.is_safe(ignore=["is_dark"]):
                time.sleep(delay)
            else:
                # Not safe, so stop waiting and return False
                self.logger.warning('Safety check failed while for twilight. Aborting.')
                return False

        # We have safely reached twilight, so return True
        return True

    def register_dark_state_completion(self):
        """ Register the completion of the taking_darks state.
        This is used to limit the number of times the darks state will be entered.
        """
        self._dark_state_times.append(current_time())

    # Private methods

    def _load_state(self, state, state_info=None):
        """ Override method to add dome logic. """
        if state_info is None:
            state_info = {}

        # Check if the state requires the dome to be open
        if state_info.pop("requires_open_dome", False):
            self.logger.debug(f"Adding state to open dome states: {state}.")
            self._dome_open_states.append(state)

        return super()._load_state(state, state_info=state_info)
