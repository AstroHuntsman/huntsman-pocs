#==============================================================================
# Docker image for a Huntsman testing environment
#==============================================================================

FROM gcr.io/panoptes-exp/panoptes-pocs:latest

ENV PANDIR_OLD=$PANDIR
ENV PANUSER=huntsman
ENV PANDIR=/var/$PANUSER
ENV POCS=$PANDIR/POCS
ENV HUNTSMAN_POCS=${PANDIR}/huntsman-pocs

# Install required packages
RUN apt-get update && \
    apt-get -y install build-essential && \
    apt-get -y install byobu sshfs vim grc sudo && \
    apt install -y openssh-server --fix-missing && \
    apt install -y openssh-client && \

    # Setup PANUSER
    useradd -m -d /home/$PANUSER $PANUSER -p $PANUSER && \
    chmod 1777 /tmp && \
    echo dialout plugdev netdev users input spi i2c gpio fuse | xargs -n 1 groupadd -f && \
    usermod -a -G dialout,plugdev,netdev,users,input,spi,i2c,gpio,fuse,sudo huntsman && \
    echo "$PANUSER ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \

    # Install Huntsman-POCS & deps
    cd $PANDIR && \
    git clone https://github.com/AstroHuntsman/huntsman-pocs.git && \
    cd $HUNTSMAN_POCS && \
    pip install -r requirements.txt && \
    pip install -e . && \
    pip install astroplan && \

    # Setup SSH so localhost works without password
    mkdir /home/$PANUSER/.ssh && \
    ssh-keygen -b 2048 -t rsa -f /home/$PANUSER/.ssh/id_rsa -N '' && \
    touch /home/$PANUSER/.ssh/authorized_keys && \
    cat /home/$PANUSER/.ssh/id_rsa.pub >> /home/$PANUSER/.ssh/authorized_keys && \
    echo "Host localhost\n\tStrictHostKeyChecking no\n" >> /home/$PANUSER/.ssh/config && \
    chown -R $PANUSER /home/$PANUSER/.ssh && \

    # Make sure permissions are correct
    chown -R $PANUSER $PANDIR && \
    chown -R $PANUSER /home/$PANUSER && \

    # Modify zshrc to get rid of panoptes stuff
    echo "export PANDIR=${PANDIR}" >> /home/$PANUSER/.zshrc && \
    echo "export POCS=${POCS}" >> /home/$PANUSER/.zshrc

#==============================================================================

WORKDIR /home/$PANUSER
ADD startup.sh /usr/local/bin/
ENTRYPOINT ["startup.sh"]
CMD ["pytest -xv --show-capture=no"]
