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

# Derive a workspace number from the workspace name
# This creates a hash of the workspace name and uses it to generate a consistent number
WORKSPACE_HASH=$(echo -n "$CONDUCTOR_WORKSPACE_NAME" | cksum | cut -f1 -d' ')
WORKSPACE_NUM=$((($WORKSPACE_HASH % 100) + 1))

BASE_DIR="$CONDUCTOR_ROOT_PATH"

# Calculate ports based on workspace number
POSTGRES_PORT=$((5432 + $WORKSPACE_NUM))
ADCP_PORT=$((8080 + $WORKSPACE_NUM))
ADMIN_PORT=$((8001 + $WORKSPACE_NUM))

echo "Derived workspace number: $WORKSPACE_NUM (from name hash)"
echo "Using ports:"
echo "  PostgreSQL: $POSTGRES_PORT"
echo "  MCP Server: $ADCP_PORT"
echo "  Admin UI: $ADMIN_PORT"

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

if [ -n "$GEMINI_API_KEY" ]; then
    echo "✓ GEMINI_API_KEY configured from environment"
else
    echo "✗ Warning: GEMINI_API_KEY not found in environment"
fi

# Copy OAuth credentials if they exist locally (not in git)
oauth_files=$(ls $BASE_DIR/client_secret*.json 2>/dev/null)
if [ -n "$oauth_files" ]; then
    for file in $oauth_files; do
        cp "$file" .
        echo "✓ Copied $(basename $file)"
        # Also update docker-compose.override.yml to mount it
        echo "✓ OAuth credentials file will be mounted in containers"
    done
else
    if [ -n "$GOOGLE_CLIENT_ID" ] && [ -n "$GOOGLE_CLIENT_SECRET" ]; then
        echo "✓ OAuth configured via environment variables"
    else
        echo "ℹ️  No OAuth credentials found - Admin UI will run without Google OAuth"
    fi
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

# Create docker-compose.override.yml for development hot reloading
cat > docker-compose.override.yml << 'EOF'
# Docker Compose override for development with hot reloading
# This file is automatically loaded by docker-compose and overrides settings in docker-compose.yml

services:
  adcp-server:
    volumes:
      # Mount source code for hot reloading, excluding .venv
      - .:/app
      - /app/.venv
      - ./audit_logs:/app/audit_logs
    environment:
      # Enable development mode
      PYTHONUNBUFFERED: 1
      FLASK_ENV: development
      WERKZEUG_RUN_MAIN: true
    # PATH is already set in Dockerfile to include .venv/bin
    command: ["python", "run_server.py"]

  admin-ui:
    volumes:
      # Mount source code for hot reloading, excluding .venv
      - .:/app
      - /app/.venv
      - ./audit_logs:/app/audit_logs
    environment:
      # Enable Flask development mode with auto-reload
      FLASK_ENV: development
      FLASK_DEBUG: 1
      PYTHONUNBUFFERED: 1
      WERKZEUG_RUN_MAIN: true
EOF
echo "✓ Created docker-compose.override.yml for development hot reloading"

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

echo ""
echo "Setup complete! Next steps:"
echo "1. Review .env file and ensure GEMINI_API_KEY is set"
echo "2. Build and start services:"
echo "   docker-compose build"
echo "   docker-compose up -d"
echo ""
echo "Services will be available at:"
echo "  MCP Server: http://localhost:$ADCP_PORT/mcp/"
echo "  Admin UI: http://localhost:$ADMIN_PORT/"
echo "  PostgreSQL: localhost:$POSTGRES_PORT"