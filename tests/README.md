# Huntsman-POCS tests

This directory contains all tests for Huntsman-POCS as well as the Docker setup to run them.

## Setup and Run tests

Before doing anything, make sure to source the environment variables. If you're unsre about this, see the [example env file](../example.huntsman.env).

```bash
# Source environment variables
source ../huntsman.env
```

_Build the image:_

```bash
# Build the tests
docker compose build
```

_Run tests:_

```bash
docker compose run --rm python_tests
```

The container can take any pytests arguments.

```bash
docker compose run --rm python_tests -s tests/test_camera.py
```

You can also run from the project root (or any other directory) by specifying the docker compose filepath:

```bash
docker compose -f /path/to/huntsman/tests/docker-compose.yml run --rm python_tests -s tests/test_camera.py
```

## Additional Information

The test container bind-mounts the following directories in the parent directory:

- `src`
  - Contains the source code to test.
- `tests`
  - Contains all tests. Probably where the compose command is being run from.
- `logs`
  - Doesn't exist in the repository. Will be created. Will contain test logs.
- `build`
  - Doesn't exist in the repository. Will be created. Will contain code coverage report.

  The benefit of bind-mounting the `src` and `tests` directories is that changes to them will not require a rebuild of the image.
