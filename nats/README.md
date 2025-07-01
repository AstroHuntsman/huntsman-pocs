# Huntsman NATS Movie Mode Setup

This repository contains the configuration and scripts for running the Huntsman telescope system in movie mode with NATS message streaming and monitoring.

## Overview

The movie mode setup includes:
- **POCS Control System**: Core telescope control and configuration
- **NATS JetStream**: High-performance message streaming for camera data
- **Memory Monitoring**: Real-time system memory usage tracking
- **Storage Management**: Tiered storage system (memory → disk)
- **SSH Tunneling**: Remote access to NATS services
- **Movie Mode Observations**: High-speed video recording for transient events

## Prerequisites

- Docker and Docker Compose
- Python 3.9+ with required packages
- Byobu (for terminal multiplexing)
- SSH access for remote connections

```bash
# Install required packages
sudo apt-get update
sudo apt-get install byobu docker.io docker-compose

# Verify installations
docker --version
docker-compose --version
byobu --version
```

## Quick Start

### 1. Environment Setup
```bash
# Set required environment variables
export PANDIR=/var/huntsman
export HUNTSMAN_POCS=/var/huntsman/huntsman-pocs

# Verify paths
ls -la $PANDIR/huntsman-config/conf_files/pocs/
ls -la $HUNTSMAN_POCS/src/
```

### 2. Start Movie Mode Services
```bash
cd /var/huntsman/huntsman-config/conf_files/pocs

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

### 3. Set Up NATS Monitoring
```bash
cd /var/huntsman/huntsman-pocs/nats

# Make script executable
chmod +x setup_nats_monitoring.sh

# Run NATS monitoring setup (creates streams and starts monitors)
./setup_nats_monitoring.sh
```

## Movie Mode Observations

### Overview

Movie mode is designed for capturing fast astronomical events (stellar occultations, transients) using very short exposures at high frame rates. Unlike standard long-exposure observations, movie mode takes many rapid frames continuously.

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
  exptime: 0.009          # 9ms exposure time
  batch_size: 1
  exp_set_size: 1
  max_frames: 200         # Maximum frames to capture
  mode: video             # Video recording mode
  frame_rate: 20.0        # Target 20 frames per second
  duration: 120           # Record for 120 seconds
  chunking_enabled: false # Single continuous recording
  filter_name:
    192.168.80.200: r_band  # All cameras use r_band filter
    # ... (all 10 cameras configured)
```

### Movie Mode Parameters Explained

| Parameter | Value | Purpose | Usage |
|-----------|-------|---------|--------|
| **`type`** | `DitheredMovieObservation` | Observation class | Triggers movie mode detection |
| **`exptime`** | `0.009` | 9ms exposure time | Very short for fast readout |
| **`frame_rate`** | `20.0` | Target FPS | Controls timing between frames |
| **`duration`** | `120` | Recording duration (seconds) | Total observation time |
| **`max_frames`** | `200` | Frame limit | Safety stop (duration × fps or max_frames) |
| **`mode`** | `video` | Recording mode | Enables video-specific features |
| **`chunking_enabled`** | `false` | File splitting | Continuous vs. chunked recording |
| **`batch_size`** | `1` | Observation batching | Process one observation at a time |
| **`exp_set_size`** | `1` | Exposures per set | Simplified for video mode |

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

#### Frame Rate Calculation
```python
frame_interval = 1.0 / frame_rate  # 1/20.0 = 0.05 seconds between frames
```

#### Duration vs Max Frames
```python
# Two limits work together:
total_frames_by_duration = duration * frame_rate  # 120 * 20 = 2400 frames
actual_frames = min(max_frames, total_frames_by_duration)  # min(200, 2400) = 200 frames
# Recording stops at whichever limit is reached first
```

#### Exposure Timing Constraints
```python
# Exposure time must be shorter than frame interval
exptime = 0.009 seconds        # 9ms exposure
frame_interval = 0.05 seconds  # 50ms between frames (20 fps)
readout_time = frame_interval - exptime  # 41ms for readout and processing
```

### Movie Mode vs Standard Observations

| Aspect | Standard Mode | Movie Mode |
|--------|---------------|------------|
| **Observation Type** | `DitheredObservation` | `DitheredMovieObservation` |
| **Method Called** | `take_observation_block()` | `take_recording_block()` |
| **Exposure Time** | 120-300 seconds | 0.009 seconds (9ms) |
| **Frame Rate** | N/A (single exposure) | 20 fps continuous |
| **Total Duration** | Single long exposure | 120 seconds of frames |
| **File Output** | Individual FITS files | Video streams/chunks |
| **Data Volume** | ~10MB per exposure | ~200 frames × 10 cameras |
| **Use Case** | Deep imaging | Transient events, occultations |

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
     - Sets exposure time to 9ms
     - Sets frame rate to 20 fps
     - Starts synchronized recording

5. **Recording Control**
   - Records for specified duration (120s) or until max_frames (200)
   - Monitors memory usage via NATS
   - Manages file output (chunked or continuous)

6. **Data Flow**
   - Raw frames → NATS memory streams → Disk streams
   - Memory monitor tracks usage
   - Storage manager moves data when memory fills

### Example Movie Mode Use Cases

#### Stellar Occultation
```yaml
observation:
  type: huntsman.pocs.scheduler.observation.movie.DitheredMovieObservation
  exptime: 0.005          # 5ms for fast events
  frame_rate: 50.0        # High frame rate
  duration: 300           # 5 minutes around predicted time
  max_frames: 15000       # 300s × 50fps
```

#### Asteroid Transit
```yaml
observation:
  type: huntsman.pocs.scheduler.observation.movie.DitheredMovieObservation
  exptime: 0.01           # 10ms exposure
  frame_rate: 30.0        # Medium frame rate
  duration: 600           # 10 minutes
  max_frames: 18000       # 600s × 30fps
```

#### Variable Star Monitoring
```yaml
observation:
  type: huntsman.pocs.scheduler.observation.movie.DitheredMovieObservation
  exptime: 0.02           # 20ms exposure
  frame_rate: 10.0        # Lower frame rate
  duration: 1800          # 30 minutes
  max_frames: 18000       # 1800s × 10fps
```

## SSH Tunneling for Remote Access

### Forward NATS Ports to Remote Server

```bash
# On Huntsman server (run in background with -f)
ssh -f -N -R 4222:localhost:4222 huntsman@203.1.111.20
ssh -f -N -R 8222:localhost:8222 huntsman@203.1.111.20  # Optional: HTTP monitoring
```

### Test Connection

```bash
# Check if ports are listening
ss -tuln | grep 4222
ss -tuln | grep 8222

# Test connectivity
nc -zv localhost 4222
nc -zv localhost 8222

# Test NATS HTTP monitoring (if port 8222 is forwarded)
curl -s http://localhost:8222/varz | jq .
```

### Manage SSH Tunnels

#### Kill Tunnel by Process Name
```bash
# Kill NATS client port tunnel
pkill -f "ssh -.*R.*4222"

# Kill NATS monitoring port tunnel  
pkill -f "ssh -.*R.*8222"
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

## Service Architecture

| Service | Container | Purpose | Ports | Health Check |
|---------|-----------|---------|-------|--------------|
| **Config Server** | `dev-pocs-config-server-mm` | POCS configuration management | 6563 | `curl localhost:6563/status` |
| **Pyro Nameserver** | `dev-pyro-name-server-mm` | Python remote objects | - | Check logs |
| **POCS Control** | `dev-pocs-control-mm` | Main telescope control | - | Interactive shell |
| **NATS JetStream** | `nats-jetstream-mm` | Message streaming | 4222, 8222 | `curl localhost:8222/varz` |

## NATS Monitoring Components

### Scripts Overview
- **`create_streams.py`**: Creates JetStream streams for camera data
- **`memory_monitor.py`**: Monitors system memory usage
- **`storage_manager.py`**: Manages tiered storage (memory → disk)
- **`setup_nats_monitoring.sh`**: Byobu setup script for all monitoring

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
cd /var/huntsman/huntsman-pocs/nats
./setup_nats_monitoring.sh

# Check system status
docker-compose ps
curl -s http://localhost:8222/varz | jq .server_name

# Access POCS control
docker exec -it dev-pocs-control-mm bash
```

### NATS Operations

```bash
# Create/recreate streams manually
cd /var/huntsman/huntsman-pocs/nats
python create_streams.py

# Delete all streams
python create_streams.py delete

# Check stream status
curl -s http://localhost:8222/jsz | jq .

# Monitor memory usage
tail -f /var/huntsman/images/memory_status.json
```

### Byobu Session Management

```bash
# Attach to monitoring session
byobu attach-session -t nats-monitoring

# Detach from session (Ctrl+F6 or)
byobu detach

# List all sessions
byobu list-sessions

# Kill monitoring session
byobu kill-session -t nats-monitoring
```

### Script Options

```bash
# Basic usage - creates streams then runs monitors
./setup_nats_monitoring.sh

# Skip creating streams if they already exist
./setup_nats_monitoring.sh --skip-create-streams

# Use a custom session name
./setup_nats_monitoring.sh --session-name my-nats-session

# Get help
./setup_nats_monitoring.sh --help
```

## Configuration

### Environment Variables

```bash
# Core paths
export PANDIR=/var/huntsman
export HUNTSMAN_POCS=/var/huntsman/huntsman-pocs

# NATS configuration
export NATS_SERVER=nats://localhost:4222
export NUM_STREAMS=10
export MEMORY_THRESHOLD=31  # Percentage

# File paths
export MEMORY_STATUS_FILE=/var/huntsman/images/memory_status.json
export STATS_FILE=/tmp/stream_stats.json
```

### Docker Compose Configuration

Key configuration files:
- `huntsman-config/conf_files/pocs/docker-compose.yaml`
- `huntsman-config/conf_files/pocs/huntsman.yaml`
- `huntsman-config/conf_files/pocs/nats-server.conf`
- `huntsman-config/conf_files/pocs/fields.yaml` (observation targets)

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

# Check camera readout speeds
# Ensure exptime + readout_time < frame_interval
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

# Check stream statistics
curl -s http://localhost:8222/jsz | jq '.streams[] | {name: .config.name, messages: .state.messages}'
```

### Reset Everything
```bash
# Stop all services
docker-compose down

# Kill NATS monitoring
byobu kill-session -t nats-monitoring

# Kill SSH tunnels
pkill -f "ssh -.*R.*4222"
pkill -f "ssh -.*R.*8222"

# Clean up (WARNING: Removes data!)
docker-compose down -v
docker system prune -f

# Start fresh
docker-compose up -d
./setup_nats_monitoring.sh
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
2. Modify target coordinates and observation parameters
3. Adjust `exptime`, `frame_rate`, `duration`, and `max_frames` as needed
4. Test with low `duration` and `max_frames` values first

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
