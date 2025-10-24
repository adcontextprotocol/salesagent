#!/bin/bash

# Test Local Sales Agent via MCP tools/call method

set -e

# Check for TEST_LOCAL_SALES_AGENT_KEY environment variable
if [ -z "$TEST_LOCAL_SALES_AGENT_KEY" ]; then
  echo "❌ Error: TEST_LOCAL_SALES_AGENT_KEY environment variable is not set"
  echo "Please set it with: export TEST_LOCAL_SALES_AGENT_KEY=your_key"
  exit 1
fi

SALES_AGENT_URL="http://localhost:8108/mcp"

echo "🔗 Testing Local Sales Agent via MCP"
echo "Endpoint: $SALES_AGENT_URL"
echo ""

# Initialize session
echo "📡 Step 1: Initialize MCP session..."

# Capture both headers and body
INIT_FULL_RESPONSE=$(curl -s -i -X POST "$SALES_AGENT_URL" \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: $TEST_LOCAL_SALES_AGENT_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}')

# Extract session ID from response headers
SESSION_ID=$(echo "$INIT_FULL_RESPONSE" | grep -i "mcp-session-id:" | sed 's/.*: //' | tr -d '\r')
echo "Session ID: $SESSION_ID"

# Parse SSE response body
INIT_JSON=$(echo "$INIT_FULL_RESPONSE" | grep "^data:" | sed 's/^data: //')

if ! echo "$INIT_JSON" | jq -e '.result' > /dev/null 2>&1; then
  echo "❌ Failed to initialize"
  echo "$INIT_JSON"
  exit 1
fi

echo "✅ Session initialized"

# Send initialized notification (required by MCP spec)
curl -s -X POST "$SALES_AGENT_URL" \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: $TEST_LOCAL_SALES_AGENT_KEY" \
  -H "mcp-session-id: $SESSION_ID" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' > /dev/null

echo ""

# List available tools
echo "📋 Step 2: List available tools..."
TOOLS_RESPONSE=$(curl -s -X POST "$SALES_AGENT_URL" \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: $TEST_LOCAL_SALES_AGENT_KEY" \
  -H "mcp-session-id: $SESSION_ID" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')

TOOLS_JSON=$(echo "$TOOLS_RESPONSE" | grep "^data:" | sed 's/^data: //')

echo "Available tools:"
echo "$TOOLS_JSON" | jq -r '.result.tools[].name'
echo ""

# Show get_products tool definition
echo "📝 get_products tool definition:"
echo "$TOOLS_JSON" | jq '.result.tools[] | select(.name == "get_products")'
echo ""

# Call get_products tool
echo "📦 Step 3: Call get_products tool..."
DISCOVER_RESPONSE=$(curl -s -X POST "$SALES_AGENT_URL" \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: $TEST_LOCAL_SALES_AGENT_KEY" \
  -H "mcp-session-id: $SESSION_ID" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_products",
      "arguments": {
        "brief": "increase brand awareness",
        "brand_manifest": {
          "url": "https://wonderstruck.org/about/",
          "name": "Wonderstruck"
        }
      }
    }
  }')

DISCOVER_JSON=$(echo "$DISCOVER_RESPONSE" | grep "^data:" | sed 's/^data: //')

echo "Discover response:"
echo "$DISCOVER_JSON" | jq '.'
echo ""

# Extract products
PRODUCTS_COUNT=$(echo "$DISCOVER_JSON" | jq -r '.result.content[0].text' | grep -o "products found" | wc -l || echo "0")

if echo "$DISCOVER_JSON" | jq -e '.result.structuredContent' > /dev/null 2>&1; then
  echo "📊 Structured content found"
  echo "$DISCOVER_JSON" | jq '.result.structuredContent'
  echo ""

  echo "🎨 First product formats:"
  echo "$DISCOVER_JSON" | jq '.result.structuredContent.items[0].creativeFormats // .result.structuredContent.items[0].formats'
fi
