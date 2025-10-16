#!/bin/bash
#
# Simple curl-based test of creative agent MCP endpoints
#
# Usage:
#   docker-compose up -d creative-agent
#   ./tests/manual/test_creative_agent_curl.sh
#

set -e

CREATIVE_AGENT_URL="http://localhost:8095"

echo "=========================================="
echo "Creative Agent MCP Direct Test (curl)"
echo "=========================================="
echo ""
echo "Testing creative agent at: $CREATIVE_AGENT_URL"
echo ""

# Test 1: Health check
echo "=========================================="
echo "1. Health Check"
echo "=========================================="
echo ""
curl -s "$CREATIVE_AGENT_URL/health" | jq . || echo "Health check failed"
echo ""

# Test 2: MCP endpoint is accessible
echo "=========================================="
echo "2. MCP Endpoint Check"
echo "=========================================="
echo ""
echo "Checking if MCP endpoint responds..."
curl -i -s "$CREATIVE_AGENT_URL/mcp/" | head -20
echo ""

# Test 3: List formats (MCP call)
echo "=========================================="
echo "3. Testing list_formats (MCP)"
echo "=========================================="
echo ""
echo "NOTE: This requires proper MCP protocol formatting"
echo "For now, just checking if endpoint is accessible"
echo ""

# Create a simple MCP request
cat > /tmp/mcp_list_formats.json <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_formats",
    "arguments": {}
  }
}
EOF

echo "Request:"
cat /tmp/mcp_list_formats.json | jq .
echo ""

echo "Response:"
curl -s -X POST "$CREATIVE_AGENT_URL/mcp/" \
  -H "Content-Type: application/json" \
  -d @/tmp/mcp_list_formats.json | jq . || echo "MCP call failed"
echo ""

# Test 4: Preview creative (MCP call)
echo "=========================================="
echo "4. Testing preview_creative (MCP)"
echo "=========================================="
echo ""

cat > /tmp/mcp_preview_creative.json <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "preview_creative",
    "arguments": {
      "creative_manifest": {
        "format_id": "display_300x250",
        "assets": {
          "image": "https://via.placeholder.com/300x250",
          "clickthrough_url": "https://example.com"
        },
        "metadata": {
          "advertiser": "Test Advertiser",
          "campaign": "Test Campaign"
        }
      }
    }
  }
}
EOF

echo "Request:"
cat /tmp/mcp_preview_creative.json | jq .
echo ""

echo "Response:"
curl -s -X POST "$CREATIVE_AGENT_URL/mcp/" \
  -H "Content-Type: application/json" \
  -d @/tmp/mcp_preview_creative.json | jq . || echo "MCP call failed"
echo ""

echo "=========================================="
echo "Testing Complete"
echo "=========================================="
