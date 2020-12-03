#!/usr/bin/env bash
# This script should be run as root.
set -eu

PANUSER=${PANUSER:-huntsman}
PANDIR=${PANDIR:-/var/huntsman}
HOME=${HOME:-/home/${PANUSER}}
LOGFILE="${PANDIR}/install-camera-pi.log"
ENV_FILE="${PANDIR}/env"

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
 if [[ ! -f "${ENV_FILE}" ]]; then
   echo "Writing environment variables to ${ENV_FILE}"
   cat >>"${ENV_FILE}" <<EOF
#### Added by install-camera-pi script ####
export PANUSER=${PANUSER}
export PANDIR=${PANDIR}
export POCS=${PANDIR}/POCS
export PANLOG=${PANDIR}/logs
#### End install-pocs script ####
EOF
  fi
  echo ". ${ENV_FILE}" >> "${HOME}/.bashrc"
}

function system_deps() {
 apt-get update | tee -a "${LOGFILE}" 2>&1
 apt-get --yes install \
   wget curl \
   git openssh-server \
   git \
   jq httpie \
   byobu | tee -a "${LOGFILE}" 2>&1
 # Add an SSH key if one doesn't exist.
 if [[ ! -f "${HOME}/.ssh/id_rsa" ]]; then
   echo "Adding ssh key"
   ssh-keygen -t rsa -N "" -f "${HOME}/.ssh/id_rsa"
 fi

 # Append some statements to .bashrc
 cat <<EOF >>/home/${PANUSER}/.bashrc
export LANG="en_US.UTF-8"

# POCS
export PANDIR=/var/huntsman
unsetopt share_history
EOF
}

function enable_auto_login() {
  # Set up autologin without password for huntsman user
  # This is a bit of a hack but it appears to be the standard method of doing this
  sed -i '/^ExecStart=$/d' /lib/systemd/system/getty@.service
  sed -i "s/ExecStart=.*/ExecStart=\nExecStart=-\/sbin\/agetty -a huntsman --noclear %I \$TERM/g" /lib/systemd/system/getty@.service
  sed -i "s/Type=idle/Type=simple/g" /lib/systemd/system/getty@.service

  # We also need to disable password change on first login
  # The easiest way of doing this is just to change the password here
  # The password expiry status can be checked by doing $chage -l ${PAUSER}
  usermod --password "${PANUSER}" "${PANUSER}"
}

# This function is responsible for setting up the byobu session / windows
# This is where we make the camera service run on login as ${PANUSER}
function setup_byobu() {
  echo -e "\n# Added by setup-byobu in install-camera-pi script" >> ${HOME}/.profile
  echo "byobu new-session -d -s ${PANUSER} -n camera-service" >> ${HOME}/.profile
  echo "byobu select-window -t camera-service" >> ${HOME}/.profile
  echo "byobu send-keys 'bash ${PANDIR}/scripts/run-camera-service.sh'" >> ${HOME}/.profile
  echo "byobu send-keys Enter" >> ${HOME}/.profile
  echo "byobu attach-session -t ${PANUSER}" >> ${HOME}/.profile
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

 echo "Setting up environment variables in ${ENV_FILE}"
 setup_env_vars

 echo "Installing system dependencies"
 system_deps

 echo "Setting up auto-login"
 enable_auto_login

 echo "Setting up byobu"
 setup_byobu

 echo "Installing docker and docker-compose"
 get_docker

 echo "Pulling docker images"
 pull_docker_images

 echo "Rebooting in 10s."
 sleep 10
 reboot
}

do_install
