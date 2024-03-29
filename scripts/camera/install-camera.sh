#!/usr/bin/env bash
# This script should be run as root.
set -eu

# Make sure we are root user
if [[ $EUID > 0 ]]
  then echo "Please run as root"
  exit
fi

PANUSER=${PANUSER:-huntsman}
PANDIR=${PANDIR:-/var/huntsman}
HOME=/home/${PANUSER}
LOGFILE="${PANDIR}/install-camera.log"

function command_exists() {
  # https://gist.github.com/gubatron/1eb077a1c5fcf510e8e5
  # this should be a very portable way of checking if something is on the path
 # usage: "if command_exists foo; then echo it exists; fi"
 type "$1" &>/dev/null
}

function make_directories() {
 mkdir -p "${HOME}/.ssh"
 mkdir -p "${PANDIR}"
 mkdir -p "${PANDIR}/logs"
 mkdir -p "${PANDIR}/images"
 mkdir -p "${PANDIR}/config_files"
 mkdir -p "${PANDIR}/.key"
 chown -R "${PANUSER}":"${PANUSER}" "${PANDIR}"
 chown -R "${PANUSER}":"${PANUSER}" "${HOME}"
}

function setup_env_vars() {
echo "Writing environment variables to bash_profile"
cat >>"${HOME}/.bash_profile" <<EOF
#### Added by install-camera script ####

export PANUSER=huntsman
export PANDIR=/var/huntsman
export POCS=${PANDIR}/POCS
export PANLOG=${PANDIR}/logs

# Define PANOPTES_CONFIG_HOST here
export PANOPTES_CONFIG_HOST=192.168.80.100

# Source profiles
if [ -f ~/.profile ]; then . ~/.profile; fi
if [ -f ~/.bashrc ]; then . ~/.bashrc; fi

#### End install-pocs script ####
EOF

# Append some statements to .bashrc
cat <<EOF >>"${HOME}/.bashrc"

#### Added by install-camera script ####
export LANG="en_US.UTF-8"
EOF
}

function system_deps() {
 apt-get update | tee -a "${LOGFILE}" 2>&1
 apt-get --yes install \
   wget curl \
   git openssh-server \
   git \
   jq httpie \
   nfs-common \
   byobu | tee -a "${LOGFILE}" 2>&1
 # Add an SSH key if one doesn't exist.
 if [[ ! -f "${HOME}/.ssh/id_rsa" ]]; then
   echo "Adding ssh key"
   ssh-keygen -t rsa -N "" -f "${HOME}/.ssh/id_rsa"
 fi
}

function enable_auto_login() {
  # Set up autologin without password for huntsman user
  # This is a bit of a hack but it appears to be the standard method of doing this
  sed -i '/^ExecStart=$/d' /lib/systemd/system/getty@.service
  sed -i "s/ExecStart=.*/ExecStart=\nExecStart=-\/sbin\/agetty -a huntsman --noclear %I \$TERM/g" /lib/systemd/system/getty@.service
  sed -i "s/Type=idle/Type=simple/g" /lib/systemd/system/getty@.service
}

# For some reason the ZWO camera/FW libraries and/or rules need to be installed outside of docker
# Otherwise we seem to be experiencing CAMERA REMOVED errors
function install_camera_libs() {
  # Download install file
  wget https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/scripts/camera/install-camera-libs.sh -O ${PANDIR}/scripts/install-camera-libs.sh
  # Install the libs and rules
  bash ${PANDIR}/scripts/install-camera-libs.sh
}

function get_docker() {
 if ! command_exists docker; then
   /bin/bash -c "$(wget -qO- https://get.docker.com)"
   apt install --yes docker-compose
 fi

 echo "Adding ${PANUSER} to docker group"
 usermod -aG docker "${PANUSER}" | tee -a "${LOGFILE}" 2>&1
}

function pull_docker_images() {
 docker pull "huntsmanarray/huntsman-pocs-camera:develop"
}

function do_install() {
 clear

 echo "Installing Huntsman software."

 echo "PANUSER: ${PANUSER}"
 echo "PANDIR: ${PANDIR}"
 echo "Logfile: ${LOGFILE}"

 echo "Creating directories in ${PANDIR}"
 make_directories

 echo "Setting up environment"
 setup_env_vars

 echo "Installing system dependencies..."
 system_deps

 echo "Setting up auto-login..."
 enable_auto_login

 echo "Setting up byobu..."
 wget https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/scripts/camera/start-byobu.sh -O ${PANDIR}/scripts/start-byobu.sh
 chmod +x ${PANDIR}/scripts/start-byobu.sh

 echo "Installing camera libs..."
 install_camera_libs

 echo "Installing docker and docker-compose..."
 get_docker

 echo "Pulling docker images..."
 pull_docker_images

 echo "Downloading run-camera-service.sh script to ${PANDIR}/scripts"
 wget https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/scripts/camera/run-camera-service.sh -O ${PANDIR}/scripts/run-camera-service.sh
 chmod +x ${PANDIR}/scripts/run-camera-service.sh

 echo "Adding camera service as reboot cronjob"
 runuser -l ${PANUSER} -c "(crontab -l ; echo '@reboot /bin/bash /var/huntsman/scripts/start-byobu.sh') | crontab -"

 echo "Rebooting in 10s."
 sleep 10
 reboot
}

do_install
