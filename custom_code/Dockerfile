# Use the huntsman-pocs image as base
FROM bsreddragon/huntsman-pocs:develop

ARG panuser=pocs-user
ENV PANUSER=$panuser

# Install git
USER "${panuser}"

RUN sudo apt-get update && \
    sudo apt-get install -y git && \
    sudo apt-get clean && \
    sudo rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /POCS
COPY --chown="${PANUSER}:${MAMBA_USER}" ./POCS .

# Set up git config and permissions
RUN git config --global --add safe.directory /POCS

# # Install with --no-deps first to bypass Python version check, then install dependencies
RUN micromamba run -n base pip install --no-cache-dir .[focuser]

WORKDIR /huntsman


# Default command
CMD ["/bin/bash"] 
