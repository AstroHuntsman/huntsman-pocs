import time


def on_enter(event_data):
    """ """
    pocs = event_data.model
    pocs.next_state = 'starting'

    # Reset the observing run
    pocs.say("Resetting observing run from sleeping state.")
    pocs.reset_observing_run()

    # Wait for startup horizon
    if not pocs.is_dark(horizon="startup"):

        check_delay = pocs.get_config('wait_delay', default=120)

        pocs.say("Waiting for startup horizon from sleeping state.")

        while not pocs.is_dark(horizon="startup"):
            if not pocs.observatory.is_safe(horizon='startup'):
                pocs.say("Weather has become unsafe while sleeping, closing dome.")
                pocs.observatory.close_dome()
            time.sleep(check_delay)

        pocs.say("Finished waiting for startup horizon.")
