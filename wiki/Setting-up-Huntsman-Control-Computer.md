This page describes how to do a clean install of everything that is required to run Huntsman POCS.

> Note: This setup assumes Huntsman POCS will be installed on Linux. Most of the working code is done via docker so it might be possible to run on Windows or OSX, but that is not currently supported by this document.

## Huntsman-POCS

Huntsman POCS runs as a series of "services" inside a [docker](https://docker.io) containers. A docker container is like a small virtual machines with a specialized task. We run a few of these specialized services on the **host** computer, which for Huntsman is the main control computer, while for a developer this would be your laptop or desktop.

There is a little bit of set up to do on the host to get set up. Almost all of the commands below will be executed on the host.

### Setup host environment

To set up the host we need to do a few things:

- Create a project directory to store our files (e.g. config files, targets, environment file, etc).

  This folder on the host can be shared as **volumes** inside a running docker service. A volume is simply a directory on the file system.

- Set environment variables.

  There are a few environment variables that we use that are accessed on the host and inside docker containers. These will mostly point to the location of the project directory.

- Install host software.

  This will mainly be `docker` and a minimal custom python environment via `anaconda`.

- Pull github respositories.

  Because we will probably be doing some development on the host we will clone the repositories on the host and volume map our changes into the running docker services.

- Pull/build docker images.

  Either locally build the `huntsman-pocs` image or pull from a docker provider.

### Create Project Directories

We will create a single directory that will host all the files needed for Huntsman POCS.

For the Huntsman Telescope, the project directory is located at `/var/huntsman`.

If you are a developer you can create this directory wherever you would like. We will setup the environment variables (below) to point to the correct location.

For this example, we will create the `/var/huntsman` directory and give our user (you) the permissions to access this directory, since it is located in `/var`.

> Note that you need `sudo` permissions to create a directory in `/var`. If you do not have `sudo` permissions (or the command below fails), you can use `~/pandir/`, which will be placed in your home directory.

In the examples below we assume the currently logged in user is `huntsman`. If you are a developer you can either create a new user on your system or set the `$PANUSER` in the environment variables below.

```sh
# Create the directory as super user.
sudo mkdir -p /var/huntsman

# Give permissions to current user.
sudo chown -R $USER:$USER /var/huntsman

# Create sub directories as user.
mkdir -p /var/huntsman/logs
mkdir -p /var/huntsman/images
```

### Setup Environment Variables

We will create an environment variable file named `env` that will contain our environment variables and then set our shell to read this file.

> Note: There is a slight circular logic to this setup in that we will put our `env` file inside our project directory and then create a variable to point to the project directory. Later we will point our shell to point to the specific env file (hard-coded in your shell setup), which breaks the circular setup and allows us to source the environment file from the project directory itself.

```
# Change to the project directory
cd /var/huntsman

# Write out to the env file.
cat <<EOF > env
export PANUSER=huntsman
export PANDIR=/var/huntsman
export PANLOG="${PANDIR}/logs"
export POCS="${PANDIR}/POCS"
export HUNTSMAN_POCS="${PANDIR}/huntsman-pocs"
export PANOPTES_CONFIG_HOST="0.0.0.0"
export PANOPTES_CONFIG_PORT=6563
export PANOPTES_CONFIG_FILE="${PANDIR}/huntsman-config/huntsman.yaml"
EOF

# Source the file into the current shell NOTE THE FIRST PERIOD.
. ./env

# echo a sourced variable
echo $HUNTSMAN_POCS

# Source the file in your shell startup so always available
# Change to appropriate shell rc file.
cat <<EOF >> ~/.bashrc
# Source the Huntsman POCS env vars
source "${PANDIR}/env"

EOF
```

### Setup Host Software

#### Docker

The easiest way to get docker on linux is to follow the instructions at the top of [get.docker.com](https://get.docker.com/), namely:

```sh
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

This should guide you through the rest of the set up process. Not that you will need to follow their directions to add your user to the `docker` group, which will likely require you to log in and out.

#### Python environment (anaconda)

We will use a script to install a minimal version of anaconda called [Miniforge](https://github.com/conda-forge/miniforge/) that defaults to using the community [`conda-forge`](http://conda-forge.org) channel for packages.

```sh
# Grab the install file for amd64 arch (use the arm64 for a Raspberry Pi)
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -O install-miniforge.sh

# Run the installer
bash install-miniforge.sh
```

After accepting the license, the above script will ask a few questions about default locations, etc.

When the script is running it will ask if you would like to initialize miniforge and make sure to type `yes`.

Start a new terminal and type `conda info` to verify information about the install.

We will create a specific python 3.9 environment called `huntsman-pocs`.

```sh
# Create the enviornment, confirming when prompted.
conda create --yes -n huntsman-pocs python=3.9

# Update shell rc to activate by default.
cat <<EOF >> ~/.bashrc
conda activate huntsman-pocs
EOF
```

After starting a new shell you should see `huntsman-pocs` set as the default environment.

### Clone Github Repositories

> Note: you may need to set up your `git` credentials.

```sh
cd $PANDIR
git clone https://github.com/panoptes/panoptes-utils.git
git clone https://github.com/panoptes/POCS.git
git clone https://github.com/AstroHuntsman/huntsman-pocs.git
```

#### Install modules

We will install the `panotpes-utils` module into the environment so that we have access to some of the `panoptes-config-server` commands.

```sh
# Go to utils dir.
cd $PANDIR/panoptes-utils/

# Install in develop mode
pip install -e .

# Check that commands work (you may need to type 'rehash' first)
panoptes-config-server --help
```

### Get Docker Images

We will pull down two docker images from POCS and then build a `huntsman-pocs` image locally.

> Note: These are large files and will use bandwidth and space.

> Note: We are using the `develop` tags for all images.

```sh
# Get panoptes-utils image.
docker pull gcr.io/panoptes-exp/panoptes-utils:develop

# Get POCS image.
docker pull gcr.io/panoptes-exp/panoptes-utils:develop

# Check successful download.
docker images
```

We are going to then build the `huntsman-pocs:develop` image locally as this is currently not stored on a server.

```sh
# Go to cloned directory
cd $HUNTSMAN_POCS

# Build the docker image.
scripts/setup-local-environment.sh

# After building, verify image.
```

### Misc Post Setup

> NOTE: The following is likely outdated. wtgee Oct 2020.

#### Weather

Huntsman uses [agg-weather](https://github.com/panoptes/aag-weather/tree/master) to read weather data and share it with a `POCS` instance. We can use its `docker` image:

```
# Get the latest docker image
docker pull gcr.io/panoptes-exp/aag-weather
```

The following should appear in `huntsman_local.yaml`:

```
environment:
  ...
  ...
  weather:
    ...
    ...
    url: http://localhost:5000/latest.json
```

#### Data download

We need to download the astrometry.net index files as well as a coordinate database.

```
cd $POCS && python pocs/utils/data.py
```

#### crontab

The coordinate database downloaded above needs to be downloaded regularly to ensure accurate
coordinates. In order to do this we add an entry to the crontab:

> Note: The default editor for crontab is vim. If you don't know how to use vim ask a friend for help here.

Type `crontab -e` to edit the crontab and then enter the following line:

```
* 12 * * 0 /Users/huntsman/anaconda3/envs/huntsman-pocs-env/bin/python $POCS/pocs/utils/data.py
```

This will cause the files to be downloaded every Sunday (`0`) at noon (`12`).

#### Setup NFS server

The NFS (network file system) server runs on the control computer so that the cameras can easily write new data to a shared images directory.

```
sudo apt -y update
sudo apt install -y nfs-kernel-server

# Edit the line below to replace the Xs with the corresponding numbers in the CC IP address
sudo cat '/var/huntsman/images  XXX.XXX.XX.0/24(rw,sync,no_subtree_check)' >> /etc/export

sudo exportfs -a
sudo systemctl restart nfs-kernel-server
```

