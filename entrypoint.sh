#!/bin/bash
set -e

echo "🚀 Starting AdCP Sales Agent..."

# Run database migrations
echo "📦 Running database migrations..."
python migrate.py

# Start the server
echo "🌐 Starting MCP server..."
exec python scripts/run_server.py