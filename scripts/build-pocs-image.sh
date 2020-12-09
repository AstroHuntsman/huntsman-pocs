#!/bin/bash
set -eu

echo "Setting up docker buildx..."
docker buildx create --use

cd ${POCS}
# echo "Building POCS image..."
docker buildx build \
  -f docker/Dockerfile \
  --platform linux/arm64 \
  --tag huntsmanarray/panoptes-pocs:fix \
  --pull=false \
  --output "type=image,push=true" .
