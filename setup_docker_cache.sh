#!/bin/bash
# setup_docker_cache.sh - Initialize Docker caching for Conductor workspaces

echo "Setting up Docker caching for AdCP Conductor workspaces..."
echo ""

# Enable BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Create global cache volumes if they don't exist
echo "Creating shared cache volumes..."

# Check if volumes exist
if docker volume inspect adcp_global_pip_cache >/dev/null 2>&1; then
    echo "✓ Volume 'adcp_global_pip_cache' already exists"
else
    docker volume create adcp_global_pip_cache
    echo "✓ Created volume 'adcp_global_pip_cache'"
fi

if docker volume inspect adcp_global_uv_cache >/dev/null 2>&1; then
    echo "✓ Volume 'adcp_global_uv_cache' already exists"
else
    docker volume create adcp_global_uv_cache
    echo "✓ Created volume 'adcp_global_uv_cache'"
fi

# Skip local registry for now - it's optional for caching
echo "✓ Using Docker BuildKit cache mounts (no registry needed)"

# Create .dockerignore if it doesn't exist
if [ ! -f .dockerignore ]; then
    echo "Creating .dockerignore file..."
    cat > .dockerignore << 'EOF'
# Python
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
.venv
venv/
ENV/
env/

# Testing
.pytest_cache
.coverage
htmlcov/
.tox/
.nox/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project specific
audit_logs/
*.log
.env
.env.*
conductor_ports.json

# Git
.git/
.gitignore

# Docker
docker-compose.override.yml
Dockerfile.*
.dockerignore

# Conductor workspaces
.conductor/
EOF
    echo "✓ Created .dockerignore file"
fi

# Update docker-compose.override.yml to use BuildKit
if [ -f docker-compose.override.yml ]; then
    echo ""
    echo "Updating docker-compose.override.yml for BuildKit..."
    
    # Check if BuildKit settings already exist
    if ! grep -q "DOCKER_BUILDKIT" docker-compose.override.yml; then
        # Append BuildKit configuration
        cat >> docker-compose.override.yml << 'EOF'

# BuildKit configuration for faster builds
x-build-args: &build-args
  DOCKER_BUILDKIT: 1
  BUILDKIT_INLINE_CACHE: 1

services:
  adcp-server:
    build:
      args:
        <<: *build-args
      cache_from:
        - localhost:5000/adcp-sales-agent:buildcache
    environment:
      DOCKER_BUILDKIT: 1

  admin-ui:
    build:
      args:
        <<: *build-args
      cache_from:
        - localhost:5000/adcp-sales-agent:buildcache
    environment:
      DOCKER_BUILDKIT: 1
EOF
        echo "✓ Added BuildKit configuration to docker-compose.override.yml"
    else
        echo "✓ BuildKit configuration already present in docker-compose.override.yml"
    fi
fi

# Create convenience script for building with cache
cat > build_with_cache.sh << 'EOF'
#!/bin/bash
# Build with maximum caching efficiency

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "Building with Docker BuildKit caching..."

# Build with BuildKit enabled
docker compose build "$@"

echo "✓ Build complete with caching"
EOF
chmod +x build_with_cache.sh

echo ""
echo "✅ Docker caching setup complete!"
echo ""
echo "To use the optimized caching:"
echo ""
echo "1. For individual builds:"
echo "   ./build_with_cache.sh"
echo ""
echo "2. For docker-compose with caching:"
echo "   export COMPOSE_FILE=docker-compose.yml:docker-compose.buildkit.yml"
echo "   docker compose build"
echo ""
echo "3. Add to your shell profile for permanent BuildKit:"
echo "   echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc"
echo "   echo 'export COMPOSE_DOCKER_CLI_BUILD=1' >> ~/.bashrc"
echo ""
echo "Cache volumes created:"
echo "  - adcp_global_pip_cache (shared pip cache)"
echo "  - adcp_global_uv_cache (shared uv cache)"
echo ""
echo "These caches are shared across ALL Conductor workspaces!"