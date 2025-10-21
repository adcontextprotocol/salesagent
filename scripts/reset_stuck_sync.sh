#!/bin/bash
# Reset stuck GAM inventory sync
#
# Usage: ./scripts/reset_stuck_sync.sh <tenant_id>
#
# Example: ./scripts/reset_stuck_sync.sh accuweather

set -e

if [ -z "$1" ]; then
    echo "Error: tenant_id required"
    echo "Usage: $0 <tenant_id>"
    echo "Example: $0 accuweather"
    exit 1
fi

TENANT_ID="$1"
BASE_URL="${BASE_URL:-https://adcp-sales-agent.fly.dev}"

echo "🔄 Resetting stuck inventory sync for tenant: $TENANT_ID"
echo "Target: $BASE_URL"
echo ""

# Note: You'll need to be logged into the admin UI to have a valid session cookie
# Or you can set the SESSION_COOKIE environment variable

if [ -n "$SESSION_COOKIE" ]; then
    COOKIE_HEADER="Cookie: session=$SESSION_COOKIE"
else
    echo "⚠️  Note: This requires an active admin UI session."
    echo "   Option 1: Log into admin UI in your browser first"
    echo "   Option 2: Set SESSION_COOKIE environment variable"
    echo ""
    read -p "Press Enter to continue with browser session, or Ctrl+C to cancel..."
    COOKIE_HEADER=""
fi

# Call reset endpoint
response=$(curl -s -X POST \
    "$BASE_URL/admin/tenant/$TENANT_ID/gam/reset-stuck-sync" \
    -H "Content-Type: application/json" \
    ${COOKIE_HEADER:+-H "$COOKIE_HEADER"} \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

echo "Response ($http_code):"
echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
echo ""

if [ "$http_code" = "200" ]; then
    echo "✅ Success! Stuck sync has been reset."
    echo ""
    echo "Next steps:"
    echo "1. Go to Admin UI → $TENANT_ID → Inventory"
    echo "2. Click 'Sync Inventory' to start a fresh sync"
    echo ""
    echo "Or use API:"
    echo "  curl -X POST $BASE_URL/admin/tenant/$TENANT_ID/gam/sync-inventory \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"mode\": \"full\"}'"
elif [ "$http_code" = "404" ]; then
    echo "ℹ️  No stuck sync found. This is normal if:"
    echo "  - Sync already completed"
    echo "  - Sync was already reset"
    echo "  - No sync is currently running"
elif [ "$http_code" = "401" ] || [ "$http_code" = "403" ]; then
    echo "❌ Authentication required."
    echo ""
    echo "Please either:"
    echo "1. Log into the admin UI in your browser, then run this script"
    echo "2. Or set SESSION_COOKIE environment variable:"
    echo "   export SESSION_COOKIE='your-session-cookie'"
    echo "   $0 $TENANT_ID"
else
    echo "❌ Error resetting sync (HTTP $http_code)"
fi
