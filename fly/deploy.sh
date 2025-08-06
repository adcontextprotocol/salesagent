#!/bin/bash
# Quick deployment script for AdCP Sales Agent on Fly.io

set -e

echo "Deploying AdCP Sales Agent to Fly.io..."

# Check if app exists
if fly apps list | grep -q "adcp-sales-agent"; then
    echo "App already exists, proceeding with deployment..."
else
    echo "Creating Fly app..."
    fly apps create adcp-sales-agent --region iad
fi

# Check if we need to create PostgreSQL
if ! fly postgres list | grep -q "adcp-db"; then
    echo "PostgreSQL not found. Would you like to create it? (y/n)"
    read -r response
    if [[ "$response" == "y" ]]; then
        ./fly/setup-postgres.sh
    else
        echo "Skipping PostgreSQL setup. Make sure DATABASE_URL is configured."
    fi
fi

# Check if we need to create volume
if ! fly volumes list | grep -q "adcp_data"; then
    echo "Creating persistent volume..."
    fly volumes create adcp_data --region iad --size 10 --yes
fi

# Deploy
echo "Starting deployment..."
fly deploy

echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Set secrets if not already done: ./fly/setup-secrets.sh"
echo "2. Initialize database (first time): fly ssh console -C 'cd /app && python init_database.py'"
echo "3. Access MCP Server: fly open"
echo "4. Access Admin UI: fly open --port 8001"