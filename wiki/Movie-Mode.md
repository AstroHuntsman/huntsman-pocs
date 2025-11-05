# Movie Mode

The Huntsman telescope has developed its own high-framerate capture mode, called _Movie Mode_. Because of its high throughput, Movie mode requires a different setup and approach to the traditional capture mode.

## The Details

The traditional capture mode writes each of the images to an NFS (network) share directory, which is then pickup up by the control server. This is infeasible for Movie mode as file throughput is too slow.

Instead, we use the high-performance publish/subscribe (pub/sub) system - [NATS Jetstream](https://docs.nats.io/nats-concepts/jetstream).

The movie mode setup includes the following components

- **Control**
  - **POCS Control System**: Core telescope control and configuration
  - **[NATS JetStream Server](https://docs.nats.io/nats-concepts/jetstream)**: High-performance message streaming for camera data using a [Pub/Sub model](##Pub-Sub).
    - **[JetStream Streams](https://docs.nats.io/nats-concepts/jetstream/streams):** The data streams that make publishes messages (images) available to consumers.
  - **Memory Monitoring**: Real-time system memory usage tracking
  - **Storage Management**: Tiered storage system (memory → disk)
  - **SSH Tunneling**: To open ports between the Control and Remote servers for data transfer via NATS Jetstream
  <!-- TODO: Check if tunneling still required -->
- **Cameras**
  - **[Pyro](https://github.com/irmen/pyro5)**: Python Remote Objects. Allows Python objects to communicate over networks
- **Remote**
  - **[Jetstream Consumers](https://docs.nats.io/nats-concepts/jetstream/consumers):** Subscribes to messages from streams. Used to recieve image data.

### Pub/Sub

Pub/Sub is a messaging system that treats the producer of information (publisher) as separate from the consumer (subscriber). Rather than sending a message directly to a consumer, the producer publishes it to some channel (i.e. _stream_). Any number of consumers can subscribe to this channel and recieve all data published to it.

In the case of Huntsman, each camera hosts two publishers which each write to their own channel (i.e. _subject_) and each of these publishers has a corresponding consumer on the remote server that subscribes to these two streams.

![pubsub-model](images/pubsub-model.png)

There are two streams per camera - a memory and a disk stream. By default, messages are published to the memory stream. This is imperative for throughput. However, should the memory usage surpass a predefined threshold, messages will be published to the disk until memory usage is back to acceptable levels.

## Setup

### Environment Variables

To run movie mode for the first time, you'll need to configure your environment variables. This is described in more detail in the [Environment and Configuration](Environment-and-Configuration#environment-variables) section.

Source the environment before running any scripts.

```bash
source huntsman.env
```

### Config File

In addition to the environment variables, a dedicated config file manages most of the telescope specifics. The requirements of this are not covered by this repository, but can be found in the [config repository](https://github.com/AstroHuntsman/huntsman-config).

### Docker Images

The NATS setup relies on Docker containers for the majority of its runtime applications. The [build script](https://github.com/AstroHuntsman/huntsman-pocs/blob/main/scripts/setup_docker_images.sh) that will build each of the required images.

There are four docker images that need to be built. Two from the base Panoptes and two Huntsman images that build from it.

You can quickly build these with the build script

```bash
$HUNTSMAN_POCS/scripts/build_push_images.sh

# Optionally, don't push the images to Docker Hub. By default, images will be pushed to the DOCKER_USER's repository
$HUNTSMAN_POCS/scripts/build_push_images.sh --no-push

# If you've already build the panoptes images and don't want to have to rebuild (their tags are static)
$HUNTSMAN_POCS/scripts/build_push_images.sh --no-pan-utils --no-pan-pocs
```

Note that this will employ the tags and username that is defined in the sourced [environment](#environment-variables).

### SSH Configuration

This is a distributed setup that is primarily managed via SSH. To assist with ease-of-use, `~/.ssh/config` use is employed.

We need to set up the following _host aliases_ for the following **hosts**:

- **Control**
  - _Remote server_
  - _Cameras 1 to 10_
- **Camera**
  - _Control server_
- **Remote**
  - _Control server_

Each SSH alias looks like this in the `~/.ssh/config` file of the host:

```bash
Host hostname1
    HostName xxx.xxx.xxx.xxx
    User Username
    IdentityFile ~/.ssh/hostname1_key
```

Note the use of an IdentityFile. We will similarly employ the use of SSH keys between each of the hosts. There are numerous guides available online detailing how to set up SSH keys between hosts so this will not be repeated here.

This setup has the enormous advantage of seemless connectivity between each of our distributed components.

### Services

The rest of the setup is done in the huntsman-pocs-config repository. There are separate files marked 'movie' for use with movie mode observation setup. Most notable is the change in the `fields.yaml` file:

```yaml
field:
  name: M31_1
  position: 00h42m44.33s 41d16m07.5s
  type: huntsman.pocs.scheduler.field.DitheredField
  dither_kwargs:
    pattern_offset: 30
    random_offset: 10
observation:
  type: huntsman.pocs.scheduler.observation.movie.DitheredMovieObservation
  priority: 9000
  exptime: 0.009 # 9ms exposure time
  batch_size: 1
  exp_set_size: 1
  max_frames: 200 # Maximum frames to capture
  mode: video # Video recording mode
  frame_rate: 2.0 # Target 2.0 frames per second
  duration: 120 # Record for 120 seconds
  chunking_enabled: false # Single continuous recording
  filter_name:
    192.168.80.200: r_band # All cameras use r_band filter
    # ... (all 10 cameras configured)
```

| Parameter              | Value                      | Purpose                      | Usage                                      |
| ---------------------- | -------------------------- | ---------------------------- | ------------------------------------------ |
| **`type`**             | `DitheredMovieObservation` | Observation class            | Triggers movie mode detection              |
| **`exptime`**          | `0.009`                    | 9ms exposure time            | Very short for fast readout                |
| **`frame_rate`**       | `20.0`                     | Target FPS                   | Controls timing between frames             |
| **`duration`**         | `120`                      | Recording duration (seconds) | Total observation time                     |
| **`max_frames`**       | `200`                      | Frame limit                  | Safety stop (duration × fps or max_frames) |
| **`mode`**             | `video`                    | Recording mode               | Enables video-specific features            |
| **`chunking_enabled`** | `false`                    | File splitting               | Continuous vs. chunked recording           |
| **`batch_size`**       | `1`                        | Observation batching         | Process one observation at a time          |
| **`exp_set_size`**     | `1`                        | Exposures per set            | Simplified for video mode                  |

There are only two fields in `huntsman.yaml` that require altering for movie mode:

```yaml
scheduler:
  # fields_file: fields.yaml
  fields_file: fields-movie.yaml
  # is_video: false
  is_video: true
```

Once set, run the huntsman movie mode services with

```bash
# Start all containerised services on the Control server
docker compose -f $HUNTSMAN_CONFIG/conf_files/pocs/docker-compose-movie.yaml up -d

# Check status
docker compose ps
```

## Run

After completing the setup process, start the rest of the services including the memory monitor (control), the streams (control), the consumers (remote) and the pyro server (camera) with the NATS startup script.

```bash
$HUNTSMAN_POCS/scripts/setup_nats.sh
```

This script attempts to do this following things:

- Set up the SHH tunnel with the remote server
- Creates a new byobu session
- Sets up steams, monitoring and storage management
- Starts the consumers on the remote server
- Sets up camera service on each camera

This script will check all required environment variables, the SSH tunnel and SSH connectivity before setting up the rest of the system.

Provided it succeeds, instructions will be displayed describing how to connect to the byobu session and monitor the system.

It is possible that the script runs without apparent error, but not all components have started successfully. For this reason, it is recommended that the user check each of the windows for signs of error or incomplete setup.

## Output

<!-- TODO: fill this in-->
