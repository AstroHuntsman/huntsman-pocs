def on_enter(event_data):
    """ Take dark images state.
    """
    pocs = event_data.model

    try:

        pocs.say("It's time to take darks!")

        # Wait until mount is parked
        pocs.say("Everything set up for darks")

        exptimes_list = list()
        for target in pocs.observatory.scheduler.fields_list:
            exptime = target['exptime']
            if exptime not in exptimes_list:
                exptimes_list.append(exptime)

        pocs.say("I'm starting with dark exposures")
        pocs.observatory.take_dark_images(exptimes_list)

    except Exception as e:
        pocs.logger.warning("Problem encountered while taking darks: {}".format(e))

    finally:
        pocs.say("Going to housekeeping state.")
        pocs.next_state = 'housekeeping'
