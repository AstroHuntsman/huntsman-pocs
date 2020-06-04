def on_enter(event_data):
    """taking_darks State
    """
    pocs = event_data.model

    try:

        pocs.say("It's time to take darks!")

        pocs.status()

        # Wait until mount is parked
        pocs.say("Everything set up for dark fields")

        exptimes_list = list()
        for target in pocs.observatory.scheduler.fields_list:
            exptime = target['exptime']
            if exptime not in exptimes_list:
                exptimes_list.append(exptime)

            if len(exptimes_list) > 0:
                pocs.say("I'm starting with dark-field exposures")
                pocs.observatory.take_dark_fields(exptimes_list)
    except Exception as e:
        pocs.logger.warning("Problem encountered while taking darks: {}".format(e))

    pocs.next_state = 'housekeeping'
