#!/bin/bash
# Quick sync check with shorter timeout

TENANT_ID="accuweather"
BASE_URL="https://adcp-sales-agent.fly.dev"

if [ -z "$TENANT_MGMT_API_KEY" ]; then
    echo "❌ TENANT_MGMT_API_KEY not set"
    exit 1
fi

echo "Checking sync history (10s timeout)..."
curl -s --max-time 10 \
    "$BASE_URL/admin/api/sync/history/$TENANT_ID?limit=5" \
    -H "X-API-Key: $TENANT_MGMT_API_KEY" | python3 -m json.tool

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Checking sync stats (10s timeout)..."
curl -s --max-time 10 \
    "$BASE_URL/admin/api/sync/stats" \
    -H "X-API-Key: $TENANT_MGMT_API_KEY" | python3 -m json.tool
