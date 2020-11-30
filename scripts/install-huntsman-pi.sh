#!/usr/bin/env bash
set -eu

usage() {
  echo -n "##################################################
# Install POCS and friends.
#
# Script Version: 2020-11-08
#
# This script is designed to install the PANOPTES Observatory
# Control System (POCS) on a cleanly installed Ubuntu system
# (ideally on a Raspberry Pi).
#
# This script is meant for quick & easy install via:
#
#   $ curl -fsSL https://install.projectpanoptes.org > install-pocs.sh
#   $ bash install-pocs.sh
#   or
#   $ wget -qO- https://install.projectpanoptes.org > install-pocs.sh
#   $ bash install-pocs.sh
#
# The script will do the following:
#
#   * Install docker and tools on the host computer.
#   * Install zsh and oh-my-zsh on the host computer.
#   * Install anaconda (via miniforge) on the host computer.
#   * Create the needed directory structure for POCS.
#   * Fetch and/or build the docker images needed to run.
#   * If in 'developer' mode, clone user's fork and set panoptes upstream.
#   * Write the environment variables to ${PANDIR}/env
#
# Docker Images:
#
#   ${DOCKER_BASE}/panoptes-utils
#   ${DOCKER_BASE}/pocs
#
# The script will ask if it should be installed in 'developer' mode or not.
#
# The regular install is for running units and will not create local (to the
# host system) copies of the files.
#
# The 'developer' mode will ask for a github username and will clone and
# fetch the repos. The $(docker/setup-local-enviornment.sh) script will then
# be run to build the docker images locally.
#
# If not in 'developer' mode, the docker images will be pulled from GCR.
#
# The script has been tested with a fresh install of Ubuntu 20.04
# but may work on other linux systems.
#
# Changes:
#   * 2020-07-05 - Initial release of versioned script.
#   * 2020-07-06 (wtgee) - Fix the writing of the env file. Cleanup.
#   * 2020-07-08 (wtgee) - Better test for ssh access for developer.
#   * 2020-07-09 (wtgee) - Fix conditional for writing shell rc files. Use 3rd
#                           party docker-compose (linuxserver.io) for arm.
#   * 2020-07-27 (wtgee) - Cleanup and consistency for Unit install.
#   * 2020-11-08 (wtgee) - Add zsh, anaconda. Docker from apt.
#
#############################################################
 $ $(basename $0) [--developer] [--user panoptes] [--pandir /var/panoptes]

 Options:
  DEVELOPER Install POCS in developer mode, default False.

 If in DEVELOPER mode, the following options are also available:
  USER      The PANUSER environment variable, defaults to current user (i.e. PANUSER=$USER).
  PANDIR    Default install directory, defaults to PANDIR=${PANDIR}. Saved as PANDIR
            environment variable.
"
}

ARCH="$(uname -m)"

PANUSER=${PANUSER:-huntsman}
PANDIR=${PANDIR:-/var/huntsman}
LOGFILE="${PANDIR}/install-huntsman-pi.log"
ENV_FILE="${PANDIR}/env"

GITHUB_USER="AstroHuntsman"
GITHUB_URL="https://github.com/${GITHUB_USER}"

PANOPTES_UPSTREAM_URL="https://github.com/panoptes"

# Repositories to clone.
REPOS=("POCS" "panoptes-utils" "panoptes-tutorials")

CONDA_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${ARCH}.sh"



function command_exists() {
  # https://gist.github.com/gubatron/1eb077a1c5fcf510e8e5
  # this should be a very portable way of checking if something is on the path
 # usage: "if command_exists foo; then echo it exists; fi"
 type "$1" &>/dev/null
}

function make_directories() {
 if [[ ! -d "${PANDIR}" ]]; then
   # Make directories and make PANUSER the owner.
   sudo mkdir -p "${PANDIR}"
 fi
}

 sudo mkdir -p "${PANDIR}/logs"
 sudo mkdir -p "${PANDIR}/images"
 sudo mkdir -p "${PANDIR}/config_files"
 sudo mkdir -p "${PANDIR}/.key"
 sudo chown -R "${PANUSER}":"${PANUSER}" "${PANDIR}"
}

function setup_env_vars() {
 if [[ ! -f "${ENV_FILE}" ]]; then
   echo "Writing environment variables to ${ENV_FILE}"
   cat >>"${ENV_FILE}" <<EOF
#### Added by install-pocs script ####
export PANUSER=${PANUSER}
export PANDIR=${PANDIR}
export POCS=${PANDIR}/POCS
export PANLOG=${PANDIR}/logs
#### End install-pocs script ####
EOF

   # Source the files in the shell.
   SHELLS=(".bashrc" ".zshrc")

   for SHELL_RC in "${SHELLS[@]}"; do
     SHELL_RC_PATH="$HOME/${SHELL_RC}"
     if test -f "${SHELL_RC_PATH}"; then
       # Check if we have already added the file.
       if ! grep -qm 1 ". ${PANDIR}/env" "${SHELL_RC_PATH}"; then
         echo ". ${PANDIR}/env" >>"${SHELL_RC_PATH}"
       fi
     fi
   done
 fi
}

function system_deps() {

   sudo apt-get update | sudo tee -a "${LOGFILE}" 2>&1
   sudo apt-get --yes install \
     wget curl \
     git openssh-server \
     ack \
     git \
     jq httpie \
     byobu \
     htop \
     speedometer \
     zsh | sudo tee -a "${LOGFILE}" 2>&1

 # Add an SSH key if one doesn't exist.
 if [[ ! -f "${HOME}/.ssh/id_rsa" ]]; then
   echo "Adding ssh key"
   ssh-keygen -t rsa -N "" -f "${HOME}/.ssh/id_rsa"
 fi

 # Install ZSH
 echo "Installing ZSH and friends (use --no-zsh to disable)"
 /bin/sh -c "$(wget https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)" "" "--unattended"

 # ZSH auto-suggestion plugin.
 git clone --single-branch https://github.com/zsh-users/zsh-autosuggestions \
   ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions

 sudo chsh --shell /bin/zsh "${PANUSER}"
 sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="candy"/g' /home/${PANUSER}/.zshrc
 sed -i 's/# DISABLE_UPDATE_PROMPT="true"/DISABLE_UPDATE_PROMPT="true"/g' /home/${PANUSER}/.zshrc
 sed -i 's/plugins=(git)/plugins=(git sudo zsh-autosuggestions dotenv)/g' /home/${PANUSER}/.zshrc

 # Anaconda via mini-forge.
 mkdir -p "${PANDIR}/scripts"
 wget -q "${CONDA_URL}" -O "${PANDIR}/scripts/install-miniforge.sh"
 /bin/sh "${PANDIR}/scripts/install-miniforge.sh" -b -f -p "${PANDIR}/conda"
 "${PANDIR}/conda/bin/conda" init zsh bash

 # Append some statements to .zshrc
 cat <<EOF >>/home/${PANUSER}/.zshrc
export LANG="en_US.UTF-8"

# POCS
export PANDIR=/var/huntsman
unsetopt share_history
EOF
}

function get_repos() {
 echo "Cloning repositories"
 for repo in "${REPOS[@]}"; do
   if [[ ! -d "${PANDIR}/${repo}" ]]; then
     cd "${PANDIR}"
     echo "Cloning ${GITHUB_URL}/${repo}"
     # Set panoptes as upstream if clone succeeded.
     if git clone --single-branch --quiet "${GITHUB_URL}/${repo}.git"; then
       cd "${repo}"
       git remote add upstream "${PANOPTES_UPSTREAM_URL}/${repo}"
     fi
   else
     echo "${repo} already exists in ${PANDIR}. No auto-update for now, skipping repo."
   fi
 done
}

function get_docker() {
 if ! command_exists docker; then
   /bin/bash -c "$(wget -qO- https://get.docker.com)"
 fi
 sudo apt install --yes docker.io docker-compose ctop

 echo "Adding ${PANUSER} to docker group"
 sudo usermod -aG docker "${PANUSER}" | sudo tee -a "${LOGFILE}" 2>&1
}

function pull_docker_images() {
 sudo docker pull "huntsmanarray/huntsman-pocs-camera:develop"
 sudo docker pull "gcr.io/panoptes-exp/panoptes-utils:develop"
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

 echo "Installing docker and docker-compose"
 get_docker

 echo "Pulling docker images"
 pull_docker_images

 echo "Rebooting in 10s."
 sleep 10
 sudo reboot
}

do_install
