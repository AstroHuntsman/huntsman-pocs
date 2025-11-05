# Environment and Configuration

## Environment Variables

To run movie mode for the first time, you'll need to configure your environment variables. There is an [example .env file](https://github.com/AstroHuntsman/huntsman-pocs/blob/main/example.huntsman.env) for this purpose. Copy it with

```bash
cp example.huntsman.env huntsman.env
```

This file be sourced before running any scripts.

```bash
source huntsman.env
```

Most of the variables will not need changing, but it's good to give a quick once-over to make sure. See the following guide for variable descriptors:

**System Level Configuration**

| Variable                  | Description                                                                                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **PANUSER**               | The username to use for most operations                                                                                                                                              |
| **PANDIR**                | The working directory for the Control and Camera servers                                                                                                                             |
| **PANLOG**                | The directory to store logs (on the Control server)                                                                                                                                  |
| **HUNTSMAN_POCS**         | The path to the huntsman-pocs repository repo on the Control server                                                                                                                  |
| **HUNTSMAN_DOME**         | The path to the huntsman-dome repository repo on the Control server                                                                                                                  |
| **HUNTSMAN_DRP**          | The path to the huntsman-drp repository repo on the Control server                                                                                                                   |
| **HUNTSMAN_REMOTE_HOST**  | The hostname for the Remote server. See [SSH Configuration](###SSH-Configuration) for more information.                                                                              |
| **HUNTSMAN_CONTROL_HOST** | The hostname for the Control server. See [SSH Configuration](###SSH-Configuration) for more information.                                                                             |
| **HUNTSMAN_CAMERAS**      | A JSON-structured list of Camera hostnames (`hostname`), numbers (`num`) and whether to use this camera (`use`). See [SSH Configuration](###SSH-Configuration) for more information. |
| **PANOPTES_CONFIG_HOST**  | The host running the config container                                                                                                                                                |
| **PANOPTES_CONFIG_PORT**  | The exposed config container port                                                                                                                                                    |

**Docker Configuration**
| Variable | Description |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **DOCKER_USER** | The Docker user. Will be used for naming images, pushing to Dockerhub, and pulling from the appropriate URL. e.g. `${DOCKER_USER}/huntsman-pocs` |
| **DOCKER_TAG** | The tag to use for huntsman (not panoptes) Docker images. Used for both image creation and pulling. e.g. `${DOCKER_USER}/huntsman-pocs:${DOCKER_TAG}` |
| **DOCKER_PAT** | The Docker Personal Access Token. Used to push images to Docker Hub. See [the official docs](https://docs.docker.com/security/access-tokens/) for further information. |

**Movie Mode Configuration**
| Variable | Description |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **NATS_SERVER** | The hostname and port of the NATS server, running on the Control server |
| **NATS_CONSUMER_OUTPUT_DIR** | The image output directory on the Remote server |
| **NATS_STATS_FILE** | Where to save the NATS statistics on the Control server |
| **NATS_NUM_STREAMS** | The number of JetStream streams to create |
| **NATS_NUM_CONSUMERS** | The number of JetStream consumers to create |
| **MEMORY_STATUS_FILE** | The location of the memory status file that will be accessed by the Camera and Control servers |
| **MEMORY_THRESHOLD** | If the memory of the Control server is above this percentage, will instead publish to the disk-storage stream |

## Config File

In addition to the environment variables, a dedicated config file manages most of the telescope specifics. The requirements of this are not covered by this repository, but can be found in the [config repository](https://github.com/AstroHuntsman/huntsman-config).
