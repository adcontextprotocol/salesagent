#!/bin/bash
# Sync API curl examples - Quick testing without Python

# Configuration
API_PORT="${ADMIN_UI_PORT:-8001}"
BASE_URL="http://localhost:${API_PORT}"

# Get API key from database (requires sqlite3)
API_KEY=$(sqlite3 adcp_local.db "SELECT value FROM superadmin_config WHERE key='api_key';")

if [ -z "$API_KEY" ]; then
    echo "Error: No API key found. Start the server first."
    exit 1
fi

echo "🔑 API Key: ${API_KEY:0:8}..."
echo "🌐 Base URL: $BASE_URL"
echo ""

# Get first GAM tenant
TENANT_ID=$(sqlite3 adcp_local.db "SELECT t.tenant_id FROM tenants t JOIN adapter_config ac ON t.tenant_id = ac.tenant_id WHERE ac.adapter_type='google_ad_manager' LIMIT 1;")

if [ -z "$TENANT_ID" ]; then
    echo "Error: No GAM tenants found"
    exit 1
fi

echo "📋 Using tenant: $TENANT_ID"
echo ""

# Example 1: Check sync status
echo "1️⃣ Check current sync status:"
echo "curl -X GET \\"
echo "  -H \"X-API-Key: $API_KEY\" \\"
echo "  \"${BASE_URL}/api/v1/sync/status/${TENANT_ID}\""
echo ""
curl -X GET \
  -H "X-API-Key: $API_KEY" \
  "${BASE_URL}/api/v1/sync/status/${TENANT_ID}" | jq '.'
echo ""

# Example 2: Trigger a sync
echo "2️⃣ Trigger a new sync:"
echo "curl -X POST \\"
echo "  -H \"X-API-Key: $API_KEY\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"sync_type\": \"incremental\"}' \\"
echo "  \"${BASE_URL}/api/v1/sync/trigger/${TENANT_ID}\""
echo ""
echo "Press Enter to trigger sync..."
read

RESPONSE=$(curl -s -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "incremental"}' \
  "${BASE_URL}/api/v1/sync/trigger/${TENANT_ID}")

echo "$RESPONSE" | jq '.'
SYNC_ID=$(echo "$RESPONSE" | jq -r '.sync_id')
echo ""

# Example 3: Monitor sync progress
if [ "$SYNC_ID" != "null" ]; then
    echo "3️⃣ Monitor sync progress (checking every 5 seconds):"
    for i in {1..12}; do
        sleep 5
        STATUS=$(curl -s -X GET \
          -H "X-API-Key: $API_KEY" \
          "${BASE_URL}/api/v1/sync/status/${TENANT_ID}" | jq -r '.status')
        
        echo "   Check $i: $STATUS"
        
        if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
            break
        fi
    done
fi

echo ""
echo "✅ Done! You can also use httpie for prettier output:"
echo "   http GET ${BASE_URL}/api/v1/sync/status/${TENANT_ID} X-API-Key:<YOUR_API_KEY>"
echo "   http POST ${BASE_URL}/api/v1/sync/trigger/${TENANT_ID} X-API-Key:<YOUR_API_KEY> sync_type=incremental"