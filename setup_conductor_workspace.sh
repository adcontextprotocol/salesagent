#!/bin/bash
# setup_conductor_workspace.sh - Automated setup for Conductor workspaces

# Check if Conductor environment variables are set
if [ -z "$CONDUCTOR_WORKSPACE_NAME" ]; then
    echo "Error: This script should be run within a Conductor workspace"
    echo "CONDUCTOR_WORKSPACE_NAME is not set"
    exit 1
fi

echo "Setting up Conductor workspace: $CONDUCTOR_WORKSPACE_NAME"
echo "Workspace path: $CONDUCTOR_WORKSPACE_PATH"
echo "Root path: $CONDUCTOR_ROOT_PATH"

BASE_DIR="$CONDUCTOR_ROOT_PATH"

# Check environment variables
echo ""
echo "Checking environment variables..."
MISSING_VARS=0

# Check SUPER_ADMIN_EMAILS (required)
if [ -n "$SUPER_ADMIN_EMAILS" ]; then
    echo "✓ SUPER_ADMIN_EMAILS configured: $SUPER_ADMIN_EMAILS"
else
    echo "✗ SUPER_ADMIN_EMAILS is NOT set (REQUIRED for Admin UI access)"
    MISSING_VARS=$((MISSING_VARS + 1))
fi

# Check GEMINI_API_KEY (required)
if [ -n "$GEMINI_API_KEY" ]; then
    echo "✓ GEMINI_API_KEY configured"
else
    echo "✗ GEMINI_API_KEY is NOT set (REQUIRED for creative generation)"
    MISSING_VARS=$((MISSING_VARS + 1))
fi

# Check Google OAuth (required)
if [ -n "$GOOGLE_CLIENT_ID" ] && [ -n "$GOOGLE_CLIENT_SECRET" ]; then
    echo "✓ Google OAuth configured via environment variables"
elif [ -f "$BASE_DIR/client_secret"*.json ]; then
    echo "✓ Google OAuth configured via client_secret.json file"
else
    echo "✗ Google OAuth is NOT configured (REQUIRED for Admin UI login)"
    echo "  Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables"
    MISSING_VARS=$((MISSING_VARS + 1))
fi

# Check SUPER_ADMIN_DOMAINS (optional)
if [ -n "$SUPER_ADMIN_DOMAINS" ]; then
    echo "✓ SUPER_ADMIN_DOMAINS configured: $SUPER_ADMIN_DOMAINS"
fi

if [ $MISSING_VARS -gt 0 ]; then
    echo ""
    echo "⚠️  Warning: $MISSING_VARS required environment variable(s) missing!"
    echo ""
    echo "To fix this, add the following to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "# AdCP Conductor Configuration"
    [ -z "$SUPER_ADMIN_EMAILS" ] && echo "export SUPER_ADMIN_EMAILS='your-email@example.com'"
    [ -z "$GEMINI_API_KEY" ] && echo "export GEMINI_API_KEY='your-gemini-api-key'"
    [ -z "$GOOGLE_CLIENT_ID" ] && [ ! -f "$BASE_DIR/client_secret"*.json ] && echo "export GOOGLE_CLIENT_ID='your-client-id.apps.googleusercontent.com'"
    [ -z "$GOOGLE_CLIENT_SECRET" ] && [ ! -f "$BASE_DIR/client_secret"*.json ] && echo "export GOOGLE_CLIENT_SECRET='your-client-secret'"
    echo ""
    echo "The workspace will be created but may not function properly."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Check if port management script exists
PORT_MANAGER="$BASE_DIR/manage_conductor_ports.py"
PORT_CONFIG="$BASE_DIR/conductor_ports.json"

if [ -f "$PORT_MANAGER" ] && [ -f "$PORT_CONFIG" ]; then
    echo "Using Conductor port reservation system..."
    
    # Reserve ports for this workspace
    PORT_RESULT=$(python3 "$PORT_MANAGER" reserve "$CONDUCTOR_WORKSPACE_NAME" 2>&1)
    
    if [ $? -eq 0 ]; then
        # Extract ports from the output
        POSTGRES_PORT=$(echo "$PORT_RESULT" | grep "PostgreSQL:" | awk '{print $2}')
        ADCP_PORT=$(echo "$PORT_RESULT" | grep "MCP Server:" | awk '{print $3}')
        ADMIN_PORT=$(echo "$PORT_RESULT" | grep "Admin UI:" | awk '{print $3}')
        
        echo "$PORT_RESULT"
    else
        echo "Failed to reserve ports: $PORT_RESULT"
        echo "Falling back to hash-based port assignment..."
        
        # Fallback: Derive a workspace number from the workspace name
        WORKSPACE_HASH=$(echo -n "$CONDUCTOR_WORKSPACE_NAME" | cksum | cut -f1 -d' ')
        WORKSPACE_NUM=$((($WORKSPACE_HASH % 100) + 1))
        
        # Calculate ports based on workspace number
        POSTGRES_PORT=$((5432 + $WORKSPACE_NUM))
        ADCP_PORT=$((8080 + $WORKSPACE_NUM))
        ADMIN_PORT=$((8001 + $WORKSPACE_NUM))
        
        echo "Derived workspace number: $WORKSPACE_NUM (from name hash)"
        echo "Using ports:"
        echo "  PostgreSQL: $POSTGRES_PORT"
        echo "  MCP Server: $ADCP_PORT"
        echo "  Admin UI: $ADMIN_PORT"
    fi
else
    echo "Port reservation system not found, using hash-based assignment..."
    
    # Fallback: Derive a workspace number from the workspace name
    WORKSPACE_HASH=$(echo -n "$CONDUCTOR_WORKSPACE_NAME" | cksum | cut -f1 -d' ')
    WORKSPACE_NUM=$((($WORKSPACE_HASH % 100) + 1))
    
    # Calculate ports based on workspace number
    POSTGRES_PORT=$((5432 + $WORKSPACE_NUM))
    ADCP_PORT=$((8080 + $WORKSPACE_NUM))
    ADMIN_PORT=$((8001 + $WORKSPACE_NUM))
    
    echo "Derived workspace number: $WORKSPACE_NUM (from name hash)"
    echo "Using ports:"
    echo "  PostgreSQL: $POSTGRES_PORT"
    echo "  MCP Server: $ADCP_PORT"
    echo "  Admin UI: $ADMIN_PORT"
fi

# Copy required files from root workspace
echo "Copying files from root workspace..."

# Create .env file from environment variables
echo "Creating .env file from environment variables..."

# Start with a fresh .env file
cat > .env << EOF
# Environment configuration for Conductor workspace: $CONDUCTOR_WORKSPACE_NAME
# Generated on $(date)

# API Keys (from environment)
GEMINI_API_KEY=${GEMINI_API_KEY:-}

# OAuth Configuration (from environment)
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
SUPER_ADMIN_EMAILS=${SUPER_ADMIN_EMAILS:-}
SUPER_ADMIN_DOMAINS=${SUPER_ADMIN_DOMAINS:-}
EOF

echo "✓ Created .env file with environment variables"

# Copy OAuth credentials file if it exists (legacy method)
oauth_files=$(ls $BASE_DIR/client_secret*.json 2>/dev/null)
if [ -n "$oauth_files" ]; then
    echo "ℹ️  Found OAuth credentials file (legacy method)"
    for file in $oauth_files; do
        cp "$file" .
        echo "   Copied $(basename $file)"
    done
fi

# Update .env with unique ports
echo "" >> .env
echo "# Server Ports (unique for Conductor workspace: $CONDUCTOR_WORKSPACE_NAME)" >> .env
echo "POSTGRES_PORT=$POSTGRES_PORT" >> .env
echo "ADCP_SALES_PORT=$ADCP_PORT" >> .env
echo "ADMIN_UI_PORT=$ADMIN_PORT" >> .env
echo "DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:$POSTGRES_PORT/adcp" >> .env
echo "" >> .env
echo "# OAuth Configuration (optional - admin UI will work without it)" >> .env
echo "# GOOGLE_CLIENT_ID=your-client-id-here" >> .env
echo "# GOOGLE_CLIENT_SECRET=your-client-secret-here" >> .env
echo "# SUPER_ADMIN_EMAILS=admin@example.com" >> .env

echo "✓ Updated .env with unique ports"

# Note: docker-compose.yml is not modified - ports are configured via .env file
echo "✓ Port configuration saved to .env file"

# Create docker-compose.override.yml for development hot reloading with caching
cat > docker-compose.override.yml << 'EOF'
# Docker Compose override for development with hot reloading and caching
# This file is automatically loaded by docker-compose and overrides settings in docker-compose.yml

services:
  adcp-server:
    build:
      args:
        DOCKER_BUILDKIT: 1
        BUILDKIT_INLINE_CACHE: 1
    volumes:
      # Mount source code for hot reloading, excluding .venv
      - .:/app
      - /app/.venv
      - ./audit_logs:/app/audit_logs
      # Mount shared cache volumes
      - adcp_global_pip_cache:/root/.cache/pip
      - adcp_global_uv_cache:/cache/uv
    environment:
      # Enable development mode
      PYTHONUNBUFFERED: 1
      FLASK_ENV: development
      WERKZEUG_RUN_MAIN: true
      DOCKER_BUILDKIT: 1
    # PATH is already set in Dockerfile to include .venv/bin
    command: ["python", "run_server.py"]

  admin-ui:
    build:
      args:
        DOCKER_BUILDKIT: 1
        BUILDKIT_INLINE_CACHE: 1
    volumes:
      # Mount source code for hot reloading, excluding .venv
      - .:/app
      - /app/.venv
      - ./audit_logs:/app/audit_logs
      # Mount shared cache volumes
      - adcp_global_pip_cache:/root/.cache/pip
      - adcp_global_uv_cache:/cache/uv
    environment:
      # Enable Flask development mode with auto-reload
      FLASK_ENV: development
      FLASK_DEBUG: 1
      PYTHONUNBUFFERED: 1
      WERKZEUG_RUN_MAIN: true
      DOCKER_BUILDKIT: 1

# Reference external cache volumes
volumes:
  adcp_global_pip_cache:
    external: true
  adcp_global_uv_cache:
    external: true
EOF
echo "✓ Created docker-compose.override.yml for development hot reloading with caching"

# Run Docker cache setup if not already done
if ! docker volume inspect adcp_global_pip_cache >/dev/null 2>&1; then
    echo "Setting up Docker caching infrastructure..."
    if [ -f ./setup_docker_cache.sh ]; then
        ./setup_docker_cache.sh
    else
        echo "⚠️  Warning: setup_docker_cache.sh not found. Creating cache volumes manually..."
        docker volume create adcp_global_pip_cache
        docker volume create adcp_global_uv_cache
        echo "✓ Created cache volumes"
    fi
fi

# Fix database.py indentation issues if they exist
if grep -q "for p in principals_data:" database.py && ! grep -B1 "for p in principals_data:" database.py | grep -q "^    "; then
    echo "Fixing database.py indentation issues..."
    # This is a simplified fix - in production you'd want a more robust solution
    echo "✗ Warning: database.py may have indentation issues that need manual fixing"
fi

# Set up Git hooks for this workspace
echo "Setting up Git hooks..."
if [ -f setup_hooks.sh ]; then
    ./setup_hooks.sh
else
    echo "✗ Warning: setup_hooks.sh not found. Git hooks not installed."
    echo "  To install hooks later, run: ./setup_hooks.sh"
fi

# Install UI test dependencies if pyproject.toml has ui-tests extra
if grep -q "ui-tests" pyproject.toml 2>/dev/null; then
    echo ""
    echo "Installing UI test dependencies..."
    if command -v uv &> /dev/null; then
        uv sync --extra ui-tests
        echo "✓ UI test dependencies installed"
        
        # Configure UI test environment
        if [ -d "ui_tests" ]; then
            echo "export ADMIN_UI_PORT=$ADMIN_PORT" >> .env
            echo "✓ UI tests configured for Admin UI port $ADMIN_PORT"
        fi
    else
        echo "✗ Warning: uv not found, skipping UI test setup"
    fi
fi

echo ""
echo "Setup complete! Next steps:"
echo "1. Review .env file and ensure GEMINI_API_KEY is set"
echo "2. Build and start services with caching:"
echo "   export DOCKER_BUILDKIT=1"
echo "   docker-compose build"
echo "   docker-compose up -d"
echo ""
echo "For faster builds across workspaces:"
echo "   ./build_with_cache.sh  # Uses shared cache"
echo ""
echo "Services will be available at:"
echo "  MCP Server: http://localhost:$ADCP_PORT/mcp/"
echo "  Admin UI: http://localhost:$ADMIN_PORT/"
echo "  PostgreSQL: localhost:$POSTGRES_PORT"
echo ""
echo "🚀 Docker caching enabled! Dependencies are cached in:"
echo "  - adcp_global_pip_cache (pip packages)"
echo "  - adcp_global_uv_cache (uv packages)"
if [ -d "ui_tests" ]; then
    echo ""
    echo "UI Testing:"
    echo "  Run tests: cd ui_tests && uv run python -m pytest"
    echo "  Claude subagent: cd ui_tests/claude_subagent && ./run_subagent.sh"
fi