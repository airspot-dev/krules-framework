#!/usr/bin/env sh

# Build with timestamp tag for uniqueness
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
IMAGE_NAME="krules-framework-wheels"

# Build the image
docker build --platform linux/amd64 -f Dockerfile.wheels -t ${IMAGE_NAME}:${TIMESTAMP} .

# Print instructions
echo "======================================"
echo "Build complete!"
echo "Use this in your Dockerfile:"
echo "FROM ${IMAGE_NAME}:${TIMESTAMP} AS wheels"
echo "======================================"