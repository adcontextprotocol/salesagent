#!/bin/bash
# Build with maximum caching efficiency

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "Building with Docker BuildKit caching..."

# Build with BuildKit enabled
docker compose build "$@"

echo "✓ Build complete with caching"
