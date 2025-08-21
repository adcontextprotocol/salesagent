#!/bin/bash
set -e

echo "=== Starting AdCP Sales Agent ==="
echo "Environment variables:"
env | grep -E "(SUPER_ADMIN|ADCP_|ADMIN_|DATABASE_URL)" | sort

# Run migrations
echo "Running migrations..."
python migrate.py || echo "Migration failed, continuing..."

# Start services with explicit logging
echo "Starting MCP server on port 8080..."
python run_server.py > /tmp/mcp_server.log 2>&1 &
MCP_PID=$!

echo "Starting Admin UI on port 8001..."
python -m src.admin.server > /tmp/admin_ui.log 2>&1 &
ADMIN_PID=$!

# Wait and check
sleep 5
echo "Service status:"
if kill -0 $MCP_PID 2>/dev/null; then
    echo "✓ MCP server is running (PID: $MCP_PID)"
else
    echo "✗ MCP server failed to start"
    echo "Last 20 lines of MCP log:"
    tail -20 /tmp/mcp_server.log
fi

if kill -0 $ADMIN_PID 2>/dev/null; then
    echo "✓ Admin UI is running (PID: $ADMIN_PID)"
else
    echo "✗ Admin UI failed to start"
    echo "Last 20 lines of Admin UI log:"
    tail -20 /tmp/admin_ui.log
fi

# Test endpoints
echo "Testing endpoints:"
curl -s http://localhost:8080/health && echo " ✓ MCP health check OK" || echo " ✗ MCP health check failed"
curl -s http://localhost:8001/health && echo " ✓ Admin UI health check OK" || echo " ✗ Admin UI health check failed"

# Start proxy
echo "Starting proxy on port 8000..."
exec python fly-proxy.py
