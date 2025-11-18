# Testing

Huntsman uses the [Pytest](https://docs.pytest.org/en/stable/) framework for unit and integration testing.

## Testing Environment

The pre-execution phase (in `tests/conftest.py`) sets up a number of resources, such as the Pyro and NATS servers as well as some useful fixtures. These resources are necessary for proper integration testing.

To simplify test setup and ensure test portability, the tests have their own Docker image that they expect to run in. This image uses the same Dockerfile as the Huntsman-POCS image, with only small build modifications. Keeping the same Dockerfile for running and testing ensures that the testing environment is as close to the run environment as possible.

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
