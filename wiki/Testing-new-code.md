It is possible to use the `huntsmanarray/testenv` docker image to easily test your local version of Huntsman-POCS. To do this, first you must ensure that the `$HUNTSMAN_POCS` environment variable is pointing to the root directory of huntsman-pocs. Then,

```
cd $HUNTSMAN_POCS/docker/testenv
docker-compose run testenv
```

This will automatically pull the latest docker image, run the tests and display the logs. Alternatively, you can specify which tests to run, e.g.:

```
docker-compose run testenv "pytest -v /var/huntsman/huntsman-pocs/huntsman/tests/test_states.py"
```
