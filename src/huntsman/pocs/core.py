from panoptes.utils.time import current_time
from panoptes.pocs.core import POCS
from huntsman.pocs.utils.safety import get_aat_weather


class HuntsmanPOCS(POCS):
    """ Minimal overrides to the POCS class """

    def __init__(self, *args, testing=False, **kwargs):
        self._dome_open_states = []
        super().__init__(*args, **kwargs)

        # Hack solution to provide POCS.is_safe functionality to observatory
        if not self.observatory._safety_func:
            self.logger.debug(f"Setting safety func for {self.observatory}.")
            self.observatory._safety_func = self.is_safe
        # This attribute is used to ignore AAT weather readings during tests
        self.testing = testing

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
        is_safe = super().is_weather_safe(**kwargs)

        # during tests do not check AAT weather status
        if self.testing:
            return is_safe

        # now determine safety according to AAT weather data
        try:
            aat_weather_data = get_aat_weather()
        except Exception as err:
            self.logger.debug(f'Request for AAT weather data failed: {err!r}')
            return is_safe

        if aat_weather_data is None:
            return is_safe
        else:
            # AAT rain flag returns 0 for no rain and 1 for rain
            return is_safe and not bool(aat_weather_data['is_raining'])

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
