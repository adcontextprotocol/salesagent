#!/bin/bash
"""
Launch MCP Inspector for manual testing of AdCP MCP server.

This script starts MCP Inspector pointed at our test server,
allowing for interactive testing of MCP tools with strategy support.
"""

set -e

# Configuration
TEST_SERVER_URL="${TEST_MCP_URL:-http://localhost:9080}"
INSPECTOR_PORT="${INSPECTOR_PORT:-6274}"
PROXY_PORT="${PROXY_PORT:-6277}"

echo "🔍 Launching MCP Inspector for AdCP Testing"
echo "================================================"
echo "Test Server: $TEST_SERVER_URL"
echo "Inspector UI: http://localhost:$INSPECTOR_PORT"
echo "Proxy Server: http://localhost:$PROXY_PORT"
echo ""

# Check if test server is running
echo "🔎 Checking if test server is running..."
if ! curl -s "$TEST_SERVER_URL/health" > /dev/null; then
    echo "❌ Test server not responding at $TEST_SERVER_URL"
    echo ""
    echo "Please start the test environment first:"
    echo "  docker-compose -f docker-compose.test.yml up -d"
    echo ""
    exit 1
fi

echo "✅ Test server is running"
echo ""

# Launch MCP Inspector
echo "🚀 Starting MCP Inspector..."
echo ""
echo "Inspector will be available at: http://localhost:$INSPECTOR_PORT"
echo ""
echo "Test with these authentication tokens:"
echo "  Admin Token: test_admin_123"
echo "  Advertiser Token: test_advertiser_456"
echo ""
echo "Example strategy IDs to test:"
echo "  sim_test_happy_path    - Everything works perfectly"
echo "  sim_creative_rejection - Creative policy violations"
echo "  sim_budget_exceeded    - Budget overspend scenarios"
echo "  conservative_pacing    - Production strategy (80% pacing)"
echo "  aggressive_scaling     - Production strategy (130% pacing)"
echo ""
echo "Press Ctrl+C to stop..."

# Create temporary MCP config for inspector
cat > /tmp/mcp_inspector_config.json << EOF
{
  "server_url": "$TEST_SERVER_URL/mcp/",
  "headers": {
    "x-adcp-auth": "test_advertiser_456"
  },
  "tools_to_test": [
    "get_products",
    "create_media_buy",
    "check_media_buy_status",
    "get_media_buy_delivery",
    "simulation_control"
  ]
}
EOF

# Launch inspector with our server
npx @modelcontextprotocol/inspector \
  --port $INSPECTOR_PORT \
  --proxy-port $PROXY_PORT \
  --config /tmp/mcp_inspector_config.json \
  python -c "
import sys
sys.path.insert(0, '.')
from src.core.main import mcp
import uvicorn
uvicorn.run(mcp.create_app(), host='127.0.0.1', port=9080)
"

# Cleanup
rm -f /tmp/mcp_inspector_config.json
