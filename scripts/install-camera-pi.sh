#!/usr/bin/env bash
set -eu

PANUSER=${PANUSER:-huntsman}
PANDIR=${PANDIR:-/var/huntsman}
LOGFILE="${PANDIR}/install-camera-pi.log"
ENV_FILE="${PANDIR}/env"

ARCH="$(uname -m)"
CONDA_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${ARCH}.sh"


function command_exists() {
  # https://gist.github.com/gubatron/1eb077a1c5fcf510e8e5
  # this should be a very portable way of checking if something is on the path
 # usage: "if command_exists foo; then echo it exists; fi"
 type "$1" &>/dev/null
}

function make_directories() {
 sudo mkdir -p "${PANDIR}"
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

function get_docker() {
 if ! command_exists docker; then
   sudo /bin/bash -c "$(wget -qO- https://get.docker.com)"
   sudo apt install --yes docker-compose
 fi

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
