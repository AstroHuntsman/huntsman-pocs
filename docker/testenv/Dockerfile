#==============================================================================
# Docker image for a Huntsman testing environment
#==============================================================================

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
