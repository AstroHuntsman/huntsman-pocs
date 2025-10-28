from huntsman.pocs.core import HuntsmanPOCS


def on_enter(event_data):
    """ """
    pocs: HuntsmanPOCS = event_data.model
    pocs.say("I'm parked now. Phew.")
    pocs.next_state = 'housekeeping'
