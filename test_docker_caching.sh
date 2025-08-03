#!/bin/bash
# Test script to demonstrate Docker caching benefits

echo "Docker Caching Test for Conductor Workspaces"
echo "==========================================="
echo ""

# Ensure BuildKit is enabled
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Clean up any existing test container
docker compose down 2>/dev/null

echo "Test 1: Initial build (will download dependencies)"
echo "--------------------------------------------------"
START_TIME=$(date +%s)
docker compose build adcp-server
END_TIME=$(date +%s)
INITIAL_BUILD_TIME=$((END_TIME - START_TIME))
echo "Initial build time: ${INITIAL_BUILD_TIME} seconds"
echo ""

echo "Test 2: Rebuild without changes (should use cache)"
echo "-------------------------------------------------"
START_TIME=$(date +%s)
docker compose build adcp-server
END_TIME=$(date +%s)
CACHED_BUILD_TIME=$((END_TIME - START_TIME))
echo "Cached build time: ${CACHED_BUILD_TIME} seconds"
echo ""

echo "Test 3: Rebuild after touching a source file"
echo "-------------------------------------------"
touch main.py
START_TIME=$(date +%s)
docker compose build adcp-server
END_TIME=$(date +%s)
SOURCE_CHANGE_BUILD_TIME=$((END_TIME - START_TIME))
echo "Build time after source change: ${SOURCE_CHANGE_BUILD_TIME} seconds"
echo ""

echo "Summary:"
echo "--------"
echo "Initial build: ${INITIAL_BUILD_TIME}s"
echo "Cached build: ${CACHED_BUILD_TIME}s"
echo "Source change build: ${SOURCE_CHANGE_BUILD_TIME}s"
echo ""
echo "Cache efficiency: $((100 - (CACHED_BUILD_TIME * 100 / INITIAL_BUILD_TIME)))% faster on cached builds"
echo ""

# Show cache volume sizes
echo "Cache volume sizes:"
echo "------------------"
if docker volume inspect adcp_global_pip_cache >/dev/null 2>&1; then
    echo "- pip cache: $(docker run --rm -v adcp_global_pip_cache:/cache alpine du -sh /cache 2>/dev/null | cut -f1)"
fi
if docker volume inspect adcp_global_uv_cache >/dev/null 2>&1; then
    echo "- uv cache: $(docker run --rm -v adcp_global_uv_cache:/cache alpine du -sh /cache 2>/dev/null | cut -f1)"
fi