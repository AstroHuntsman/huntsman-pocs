from panoptes.pocs.core import POCS


class HuntsmanPOCS(POCS):
    """ Minimal overrides to the POCS class """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        """ Override method to open dome if required.
        """
        state_machine = super()._load_state(state, state_info=state_info)

        # Add the callback to open the dome
        if state_info is None:
            state_info = {}
        if state_info.get("requires_open_dome", False):
            state_machine.add_callback('enter', '_open_dome')

        return state_machine

    def _open_dome(self):
        self.observatory.open_dome()
