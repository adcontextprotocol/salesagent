# Docker Caching for Conductor Workspaces

This document describes the Docker caching implementation that significantly speeds up builds across multiple Conductor workspaces by sharing downloaded dependencies.

## Overview

The caching solution provides:
- **Shared dependency cache** across all Conductor workspaces
- **BuildKit mount caches** for pip and uv packages
- **Local Docker registry** for layer caching
- **Automatic cache setup** in workspace initialization

## How It Works

### 1. Dockerfile Optimization
The Dockerfile uses BuildKit mount caches:
```dockerfile
RUN --mount=type=cache,target=/cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv sync --frozen
```

### 2. Shared Docker Volumes
Two persistent volumes store cached dependencies:
- `adcp_global_pip_cache` - Python pip packages
- `adcp_global_uv_cache` - uv package manager cache

### 3. BuildKit Cache Mounts
Docker BuildKit's cache mount feature provides efficient dependency caching without needing a registry.

## Setup

### Initial Setup (One Time)
Run the setup script to create the caching infrastructure:
```bash
./setup_docker_cache.sh
```

This will:
- Create shared cache volumes
- Configure BuildKit settings
- Create optimized build scripts

### Per-Workspace Setup
The conductor workspace setup automatically configures caching:
```bash
./setup_conductor_workspace.sh
```

## Usage

### Option 1: Use the Build Script (Recommended)
```bash
./build_with_cache.sh
```

### Option 2: Manual Build with Caching
```bash
export DOCKER_BUILDKIT=1
docker-compose build
```

### Option 3: Use BuildKit Compose File
```bash
docker compose -f docker-compose.yml -f docker-compose.buildkit.yml build
```

## Performance Impact

With caching enabled:
- **First build**: ~2-3 minutes (downloads all dependencies)
- **Subsequent builds**: ~30 seconds (uses cached dependencies)
- **New workspace builds**: ~45 seconds (uses shared cache)

Without caching:
- **Every build**: ~2-3 minutes (re-downloads everything)

## Cache Management

### View Cache Size
```bash
docker volume inspect adcp_global_pip_cache
docker volume inspect adcp_global_uv_cache
```

### Clear Caches (if needed)
```bash
docker volume rm adcp_global_pip_cache adcp_global_uv_cache
docker volume create adcp_global_pip_cache
docker volume create adcp_global_uv_cache
```


## Troubleshooting

### BuildKit Not Working
Ensure BuildKit is enabled:
```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

Add to your shell profile:
```bash
echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc
echo 'export COMPOSE_DOCKER_CLI_BUILD=1' >> ~/.bashrc
```

### Cache Volumes Missing
Re-run the setup:
```bash
./setup_docker_cache.sh
```


## Technical Details

### Cache Locations
- **Container pip cache**: `/root/.cache/pip`
- **Container uv cache**: `/cache/uv`
- **Host volumes**: Docker-managed volumes

### Environment Variables
- `UV_CACHE_DIR=/cache/uv` - uv cache location
- `UV_TOOL_DIR=/cache/uv-tools` - uv tools cache
- `DOCKER_BUILDKIT=1` - Enable BuildKit
- `BUILDKIT_INLINE_CACHE=1` - Enable inline caching

### Files Created
- `docker-compose.buildkit.yml` - BuildKit compose configuration
- `setup_docker_cache.sh` - Cache setup script
- `build_with_cache.sh` - Optimized build script
- `.dockerignore` - Excludes unnecessary files from build context