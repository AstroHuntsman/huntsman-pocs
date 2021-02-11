from panoptes.pocs.core import POCS


class HuntsmanPOCS(POCS):
    """ Minimal overrides to the POCS class """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dome_open_states = []

    def run(self, initial_next_state='starting', *args, **kwargs):
        """ Override the default initial_next_state parameter from "ready" to "starting".
        This allows us to call pocs.run() as normal, without needing to specify the initial next
        state explicitly.
        Args:
            initial_next_state (str, optional): The first state the machine should move to from
                the `sleeping` state, default `starting`.
            *args, **kwargs: Parsed to POCS.run.
        """
        return super().run(initial_next_state=initial_next_state, *args, **kwargs)

    def _load_state(self, state, state_info=None):
        """ Override method to add dome logic. """
        if state_info is None:
            state_info = {}

        # Check if the state requires the dome to be open
        requires_open_dome = state_info.pop("requires_open_dome", False)
        if requires_open_dome:
            self._dome_open_states.append(state)

        return super()._load_state(state, state_info=state_info)

    def before_state(self, event_data):
        """ Called before each state.
        Args:
            event_data(transitions.EventData):  Contains information about the event
         """
        if self.state in self._dome_open_states:
            self.say(f"Opening the dome before entering the {self.next_state} state.")
            self.observatory.open_dome()
        self.say(f"Entering {self.next_state} state from the {self.state} state.")

    def after_state(self, event_data):
        """ Called after each state.
        Args:
            event_data(transitions.EventData):  Contains information about the event
        """
        self.say(f"Finished with the {self.state} state. The next state is {self.next_state}.")
