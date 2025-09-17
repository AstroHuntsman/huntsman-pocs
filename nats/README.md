
# Huntsman NATS Movie Mode Setup

This repository contains the configuration and scripts for running the Huntsman telescope system in movie mode with NATS message streaming and monitoring.

## Overview
The system comprosises of three main components:
- **Huntsman Cameras:** Up to 10 cameras that record the data and publish it to the control server.
- **Huntsman Control:** The Control server, where data is recieved from the cameras and published to the remote server.
- **Huntsman Remote:** The Remote server, where data is recieved from the control server and stored.

The movie mode setup includes the following components
- **Control**
    - **POCS Control System**: Core telescope control and configuration
    - **[NATS JetStream Server](https://docs.nats.io/nats-concepts/jetstream)**: High-performance message streaming for camera data using a [Pub/Sub model](##Pub-Sub).
        - **[JetStream Streams](https://docs.nats.io/nats-concepts/jetstream/streams):** The data streams that make publishes messages (images) available to consumers.
    - **Memory Monitoring**: Real-time system memory usage tracking
    - **Storage Management**: Tiered storage system (memory → disk)
    - **SSH Tunneling**: To open ports between the Control and Remote servers for data transfer via NATS Jetstream
- **Cameras**
    - **[Pyro](https://github.com/irmen/pyro5)**: Python Remote Objects. Allows Python objects to communicate over networks
- **Remote**
    - **[Jetstream Consumers](https://docs.nats.io/nats-concepts/jetstream/consumers):** Subscribes to messages from streams. Used to recieve image data.

## Prerequisites

- Docker and Docker Compose
- Python 3.9+ with required packages
- Byobu (for terminal multiplexing)
- SSH access for remote connections

```bash
# Install required packages
sudo apt-get update
sudo apt-get install byobu docker.io docker-compose jq

# Verify installations
docker --version
docker-compose --version
byobu --version
```

## First Time Setup
### Environment Variables
To run movie mode for the first time, you'll need to configure your environment variables. There is an [example .env file](../example.huntsman.env) for this purpose. Copy it with

```bash
cp example.huntsman.env huntsman.env
```

Most of the variables will not need changing, but it's good to give a quick once-over to make sure. See the following guide for variable descriptors:

- **PANUSER:** The username to use for most operations
- **PANDIR:** The working directory for the Control and Camera servers
- **PANLOG:** The directory to store logs (on the Control server)
- **HUNTSMAN_POCS:** The path to the huntsman-pocs repository repo on the Control server
- **HUNTSMAN_DOME:** The path to the huntsman-dome repository repo on the Control server
- **HUNTSMAN_DRP:** The path to the huntsman-drp repository repo on the Control server
- **HUNTSMAN_REMOTE_HOST:** Then hostname for the Remote server. See [SSH Configuration](###SSH-Configuration) for more information.
- **HUNTSMAN_CONTROL_HOST:** Then hostname for the Control server. See [SSH Configuration](###SSH-Configuration) for more information.
- **HUNTSMAN_CAMERAS:** A JSON-structured list of Camera hostnames (`hostname`), numbers (`num`) and whether to use this camera (`use`).  See [SSH Configuration](###SSH-Configuration) for more information.
- **PANOPTES_CONFIG_HOST:** The host running the config container
- **PANOPTES_CONFIG_PORT:** The exposed config cotnainer port
- **NATS_SERVER:** The hostname and port of the NATS server, running on the Control server
- **NATS_CONSUMER_OUTPUT_DIR:** The image output directory on the Remote server
- **NATS_STATS_FILE:** Where to save the NATS statistics on the control server
- **NATS_NUM_STREAMS:** The number of JetStream streams to create
- **NATS_NUM_CONSUMERS:** The number of JetStream consumers to create
- **NATS_REMOTE_PYTHON_EXECUTABLE:** The path of the python environment executable on the Remote server
- **NATS_REMOTE_SCRIPT_DIR:** The directory that stores the consumer.py python file on the Remote server
- **MEMORY_STATUS_FILE:** The location of the memory status file that will be accessed by the Camera and Control servers
- **MEMORY_THRESHOLD:** If the memory of the Control server is above this percentage, will instead publish to the disk-storage stream.

### Python
You'll need to set up your Python environment on the control server. The officially supported version is 3.9. If this is not already installed, it'll need to be. There are numerous online tutorials on how to install a specific version of Python.

As for the environment, the dependencies for this project aren't pinned, so you'll need to use a dependency solver. There are a few options for these:
- [Anaconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/)
- [Mamba](https://github.com/mamba-org/mamba)
- [UV](https://github.com/astral-sh/uv)

Choose your favourite then install the project with your manager's install command.

### SSH Configuration
This is a distributed setup that is primarily managed via SSH. To assist with ease-of-use, `~/.ssh/config` use is employed. 

We need to set up the following *host aliases* for the following **hosts**:
- **Control**
    - *Remote server*
    - *Cameras 1->10*
- **Camera**
    - *Control server*
- **Remote**
    - *Control server*

Each SSH alias looks like this in the `~/.ssh/config` file of the host:
```bash
Host hostname1
    HostName xxx.xxx.xxx.xxx
    User Username
    IdentityFile ~/.ssh/hostname1_key
```

Note the use of an IdentityFile. We will similarly employ the use of SSH keys between each of the hosts.

This setup has the enormous advantage of seemless connectivity between each of our distributed components.

## Quick Start

### 1. Environment Setup

Source your `huntsman.env` file to load the correct environment variables
```bash
source huntsman.env
```

### 2. Start Movie Mode Services from Config

```bash
# Start all containerised services on the Control server
docker compose -f $HUNTSMAN_CONFIG/conf_files/pocs/docker-compose.yaml up -d

# Check status
docker-compose ps
```

### 3. Run the NATS Startup Script

```bash
$HUNTSMAN_POCS/scripts/setup_nats.sh

```
This script will check all required environment variables, the SSH tunnel and SSH connectivity before setting up the rest of the system.

Provided it succeeds, instructions will be displayed describing how to connect to the byobu session and monitor the system.

It is possible that the script runs without apparent error, but not all components have started successfully. For this reason, it is recommended that the user check each of the windows for signs of error or incomplete setup.

## Movie Mode Observations

### Overview

### Configuration in fields.yaml

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

### Movie Mode Parameters Explained

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

### Movie Mode Detection

The system detects movie mode in `huntsman-pocs/src/huntsman/pocs/states/huntsman/observing.py`:

```python
def on_enter(event_data):
    pocs = event_data.model
    observation = pocs.observatory.current_observation

    print("observation.__class__.__name__: ", observation.__class__.__name__)

    try:
        # Movie mode detection - checks if 'Movie' is in class name
        if 'Movie' in observation.__class__.__name__:
            # Uses specialized movie recording method
            pocs.observatory.take_recording_block(observation)
        else:
            # Uses standard observation method
            pocs.observatory.take_observation_block(observation)
    except Exception as err:
        pocs.logger.error(f"Exception: {err!r}")
```

### Parameter Usage and Timing

#### Frame Rate Behavior

**Important**: `frame_rate` sets the **maximum** rate, not a guaranteed rate.

- If camera captures faster than `frame_rate`: Sleep time is added to slow down to target
- If camera captures slower than `frame_rate`: No sleep added, runs at hardware maximum
- **Use realistic values** if needed

#### Duration vs Max Frames

Instead of max_frames, duration is used for ending the observation.

### Movie Mode Workflow

1. **Scheduler Creation**
   - Loads `fields.yaml` configuration
   - Creates `DitheredMovieObservation` object with movie parameters

2. **State Machine Execution**
   - Observatory enters `observing` state
   - Calls `on_enter()` function in `observing.py`

3. **Mode Detection**
   - Checks if `'Movie'` is in observation class name
   - Routes to appropriate recording method

4. **Movie Recording Execution**
   - Calls `take_recording_block(observation)`
   - Configures all 10 cameras with movie parameters:

5. **Recording Control**
   - Records for specified duration (120s)
   - Monitors memory usage via NATS
   - Manages file output (chunked or continuous)

6. **Data Flow**
   - Raw frames → NATS memory streams or Disk streams depending memory usage
   - Nats-stream container runs on main server(keeps data on memory or disk)
   - End consumers on remote server

## SSH Tunneling for Remote Access

### Forward NATS Ports to Remote Server

```bash
# On Huntsman server (run in background with -f)
ssh -f -N -R 4222:localhost:4222 huntsman@203.1.111.20
```

### Test Connection

```bash
# Check if ports are listening
ss -tuln | grep 4222

# Test connectivity
nc -zv localhost 4222
```

### Manage SSH Tunnels

#### Kill Tunnel by Process Name

```bash
# Kill NATS client port tunnel
pkill -f "ssh -.*R.*4222"
```

#### Kill Tunnel by PID

```bash
# Find the SSH tunnel process
ps aux | grep "ssh -.*R.*4222" | grep -v grep

# Kill it using the PID (first number in the output)
kill <PID>
```

#### List All SSH Tunnels

```bash
# Show all SSH reverse tunnels
ps aux | grep "ssh -.*-R" | grep -v grep
```

## NATS Monitoring Components

### Scripts Overview

- **`create_streams.py`**: Creates JetStream streams for camera data
- **`memory_monitor.py`**: Monitors system memory usage
- **`storage_manager.py`**: Manages tiered storage (memory → disk)
- **`setup_manager_monitoring.sh`**: Byobu setup script for all monitoring

### Stream Configuration

- **Memory Streams**: `CAMERA_MEMORY_0` to `CAMERA_MEMORY_9`
  - Storage: In-memory (fast)
  - Retention: 60 seconds
  - Max: 1GB per stream
- **Disk Streams**: `CAMERA_DISK_0` to `CAMERA_DISK_9`
  - Storage: File-based (persistent)
  - Retention: 2 hours
  - Max: 10GB per stream

## Usage Examples

### Basic Operations

```bash
# Start everything
cd /var/huntsman/huntsman-config/conf_files/pocs
docker-compose up -d

# create streams and start monitoring scripts
cd /var/huntsman/huntsman-pocs/nats
./setup_manager_monitoring.sh

# on remote server
cd /home/huntsman/Projects/huntsman
python start_consumers.py

# start services on telescope servers
cd /var/huntsman/
./scripts/start-byobu.sh

# Access POCS control container
docker exec -it dev-pocs-control-mm bash
python src/run_coarse_f_observing.py # run inside container

# Check system status
docker-compose ps
curl -s http://localhost:8222/varz | jq .server_name
```

### NATS Operations

```bash
# Create/recreate streams manually
cd /var/huntsman/huntsman-pocs/nats
python create_streams.py

# Delete all streams
python create_streams.py --delete

# Check stream status
curl -s http://localhost:8222/jsz | jq .

# Monitor memory usage
tail -f /var/huntsman/images/memory_status.json
```

### Byobu Session Management

```bash
# Attach to monitoring session
byobu attach-session -t huntsman-nats

# Detach from session (Ctrl+F6 or)
byobu detach

# List all sessions
byobu list-sessions

# Kill monitoring session
byobu kill-session -t huntsman-nats
```

## Configuration

### Environment Variables

The MEMORY_THRESHOLD in memory_monitor.py is currently set to 31 for testing purposes and should be adjusted for production use(60-70).

Both NUM_STREAMS and NUM_CONSUMERS should be configured to match the number of active telescopes in your system. This ensures optimal resource allocation and data processing efficiency. The default values(10) for NUM_STREAMS and NUM_CONSUMERS are typically sufficient and don't require modification.

```bash
# Core paths
export PANDIR=/var/huntsman
export HUNTSMAN_POCS=/var/huntsman/huntsman-pocs

# NATS configuration
export NATS_SERVER=nats://localhost:4222
export NUM_STREAMS=10
export NUM_CONSUMERS=10
export MEMORY_THRESHOLD=31  # Percentage

# File paths
export MEMORY_STATUS_FILE=/var/huntsman/images/memory_status.json
export STATS_FILE=/tmp/stream_stats.json
```

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check logs
docker-compose logs

# Check disk space
df -h

# Check port conflicts
netstat -tulpn | grep -E ':(4222|6563|8222)'
```

#### NATS Connection Issues

```bash
# Verify NATS is running
docker ps | grep nats
curl localhost:8222/varz

# Check NATS logs
docker-compose logs nats-mm

# Restart NATS service
docker-compose restart nats-mm
```

#### Movie Mode Issues

```bash
# Check if movie observation is detected
docker exec -it dev-pocs-control-mm bash
# Look for "observation.__class__.__name__: DitheredMovieObservation" in logs

# Verify field configuration
cat /huntsman/conf_files/fields.yaml | grep -A 20 "DitheredMovieObservation"

```

#### SSH Tunnel Problems

```bash
# Check if tunnel is active
ss -tuln | grep 4222

# Test local NATS connection
nc -zv localhost 4222

# Check SSH tunnel process
ps aux | grep "ssh -.*R.*4222"

# Restart tunnel
pkill -f "ssh -.*R.*4222"
ssh -f -N -R 4222:localhost:4222 huntsman@203.1.111.20
```

#### Memory Issues

```bash
# Check current memory usage
free -h
cat /var/huntsman/images/memory_status.json
```

### Reset Everything

```bash
# Kill consumers on remote server
pkill -f "python consumer.py"

# Kill NATS monitoring
byobu kill-session -t nats-monitoring

# Stop all services
docker-compose down

# Kill SSH tunnels - not necessary - optional
pkill -f "ssh -.*R.*4222"

# Clean up (WARNING: Removes data!)
docker-compose down -v

# not necessary - optional
docker system prune -f
```

## Monitoring and Logs

### Log Locations

- Docker logs: `docker-compose logs [service-name]`
- POCS logs: `/var/huntsman/logs/`
- NATS monitoring: Byobu session `nats-monitoring`

### Key Metrics

- Memory usage: `/var/huntsman/images/memory_status.json`
- Stream statistics: `/tmp/stream_stats.json`
- NATS server stats: `http://localhost:8222/varz`
- JetStream stats: `http://localhost:8222/jsz`

## Development

### Adding New Streams

1. Modify `NUM_STREAMS` environment variable
2. Run `python create_streams.py` to create new streams
3. Update consumer scripts if needed

### Custom Configuration

- Edit `docker-compose.yaml` for service configuration
- Modify `nats-server.conf` for NATS settings
- Update `huntsman.yaml` for POCS configuration
- Modify `fields.yaml` for observation targets and movie parameters

### Creating New Movie Observations

1. Copy existing movie observation configuration in `fields.yaml`
2. Adjust `exptime`, `frame_rate`, `duration`, and `max_frames` as needed
3. Test with low `duration` and `max_frames` values first

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review Docker and NATS logs
3. Verify SSH tunnel connectivity
4. Check system resources (memory, disk, network)
5. Validate movie mode parameters in `fields.yaml`

---

**Author**: Huntsman Telescope Team  
**Last Updated**: $(date +%Y-%m-%d)
