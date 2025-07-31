#!/bin/bash
# setup_conductor_workspace.sh - Automated setup for Conductor workspaces

# Check if workspace number is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <workspace_number>"
    echo "Example: $0 3"
    exit 1
fi

WORKSPACE_NUM=$1
BASE_DIR="../.."

# Calculate ports based on workspace number
POSTGRES_PORT=$((5432 + $WORKSPACE_NUM))
ADCP_PORT=$((8080 + $WORKSPACE_NUM))
ADMIN_PORT=$((8001 + $WORKSPACE_NUM))

echo "Setting up Conductor workspace $WORKSPACE_NUM with ports:"
echo "  PostgreSQL: $POSTGRES_PORT"
echo "  MCP Server: $ADCP_PORT"
echo "  Admin UI: $ADMIN_PORT"

# Copy required files from root workspace
echo "Copying files from root workspace..."

# Copy .env file
if [ -f "$BASE_DIR/.env" ]; then
    cp "$BASE_DIR/.env" .
    echo "✓ Copied .env file"
    
    # Check if config.json has a different Gemini API key
    if [ -f "$BASE_DIR/config.json" ]; then
        CONFIG_KEY=$(grep -o '"gemini_api_key"[[:space:]]*:[[:space:]]*"[^"]*"' "$BASE_DIR/config.json" | cut -d'"' -f4)
        if [ -n "$CONFIG_KEY" ]; then
            # Update .env with the key from config.json
            sed -i.bak "s/^GEMINI_API_KEY=.*/GEMINI_API_KEY=$CONFIG_KEY/" .env
            rm .env.bak
            echo "✓ Updated GEMINI_API_KEY from config.json"
        fi
    fi
else
    echo "✗ Warning: No .env file found in root workspace"
fi

# Copy OAuth credentials
oauth_files=$(ls $BASE_DIR/client_secret*.json 2>/dev/null)
if [ -n "$oauth_files" ]; then
    for file in $oauth_files; do
        cp "$file" .
        echo "✓ Copied $(basename $file)"
    done
else
    echo "✗ Warning: No OAuth credentials found in root workspace"
fi

# Update .env with unique ports
echo "" >> .env
echo "# Server Ports (unique for Conductor workspace $WORKSPACE_NUM)" >> .env
echo "POSTGRES_PORT=$POSTGRES_PORT" >> .env
echo "ADCP_SALES_PORT=$ADCP_PORT" >> .env
echo "ADMIN_UI_PORT=$ADMIN_PORT" >> .env
echo "DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:$POSTGRES_PORT/adcp" >> .env

echo "✓ Updated .env with unique ports"

# Update docker-compose.yml defaults
echo "Updating docker-compose.yml defaults..."
sed -i.bak "s/\${POSTGRES_PORT:-[0-9]*}/\${POSTGRES_PORT:-$POSTGRES_PORT}/g" docker-compose.yml
sed -i.bak "s/\${ADCP_SALES_PORT:-[0-9]*}/\${ADCP_SALES_PORT:-$ADCP_PORT}/g" docker-compose.yml
sed -i.bak "s/\${ADMIN_UI_PORT:-[0-9]*}/\${ADMIN_UI_PORT:-$ADMIN_PORT}/g" docker-compose.yml
rm docker-compose.yml.bak
echo "✓ Updated docker-compose.yml"

# Fix database.py indentation issues if they exist
if grep -q "for p in principals_data:" database.py && ! grep -B1 "for p in principals_data:" database.py | grep -q "^    "; then
    echo "Fixing database.py indentation issues..."
    # This is a simplified fix - in production you'd want a more robust solution
    echo "✗ Warning: database.py may have indentation issues that need manual fixing"
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