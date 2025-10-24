#!/bin/bash
# Check AccuWeather sync status in production
#
# Usage: ./scripts/check_accuweather_sync.sh

set -e

TENANT_ID="accuweather"
BASE_URL="${BASE_URL:-https://adcp-sales-agent.fly.dev}"

echo "🔍 Checking AccuWeather sync status..."
echo "Target: $BASE_URL"
echo "Tenant: $TENANT_ID"
echo ""

# Check if we have the tenant management API key
if [ -z "$TENANT_MGMT_API_KEY" ]; then
    echo "⚠️  TENANT_MGMT_API_KEY not set"
    echo "   Please set TENANT_MGMT_API_KEY environment variable"
    echo "   Example: export TENANT_MGMT_API_KEY='sk_...'"
    echo ""
    echo "Attempting without API key (may fail)..."
    API_KEY_HEADER=""
else
    API_KEY_HEADER="-H \"X-API-Key: $TENANT_MGMT_API_KEY\""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Checking sync history for $TENANT_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

response=$(curl -s ${API_KEY_HEADER:+-H "$API_KEY_HEADER"} \
    "$BASE_URL/admin/api/sync/history/$TENANT_ID?limit=5" \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Sync history retrieved:"
    echo "$body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data['total'] == 0:
    print('   ⚠️  No sync jobs found for this tenant')
else:
    print(f\"   Total sync jobs: {data['total']}\")
    print('')
    for job in data['results']:
        status_emoji = '✅' if job['status'] == 'completed' else ('❌' if job['status'] == 'failed' else '🔄')
        print(f\"   {status_emoji} {job['sync_id']}\")
        print(f\"      Type: {job['sync_type']}\")
        print(f\"      Status: {job['status']}\")
        print(f\"      Started: {job['started_at']}\")
        if job.get('completed_at'):
            print(f\"      Completed: {job['completed_at']}\")
            print(f\"      Duration: {job['duration_seconds']:.2f}s\")
        if job.get('error'):
            print(f\"      Error: {job['error']}\")
        if job.get('summary'):
            summary = job['summary']
            if 'ad_units' in summary:
                print(f\"      Ad Units: {summary['ad_units'].get('total', 0)}\")
            if 'placements' in summary:
                print(f\"      Placements: {summary['placements'].get('total', 0)}\")
        print('')
" 2>/dev/null || echo "$body"
else
    echo "❌ Failed to retrieve sync history (HTTP $http_code)"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Checking overall sync stats"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

response=$(curl -s ${API_KEY_HEADER:+-H "$API_KEY_HEADER"} \
    "$BASE_URL/admin/api/sync/stats" \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Sync stats retrieved:"
    echo "$body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"   Status counts (last 24h):\")
for status, count in data['status_counts'].items():
    emoji = '✅' if status == 'completed' else ('❌' if status == 'failed' else ('🔄' if status == 'running' else '⏳'))
    print(f\"      {emoji} {status}: {count}\")
print('')
if data.get('stale_tenants'):
    print(f\"   ⚠️  Stale tenants (no sync in >24h): {len(data['stale_tenants'])}\")
    for tenant in data['stale_tenants']:
        if tenant['tenant_id'] == 'accuweather':
            print(f\"      🔴 AccuWeather - Last sync: {tenant.get('last_sync', 'Never')}\")
        else:
            print(f\"      {tenant['tenant_id']} - Last sync: {tenant.get('last_sync', 'Never')}\")
else:
    print('   ✅ All tenants synced recently')
" 2>/dev/null || echo "$body"
else
    echo "❌ Failed to retrieve sync stats (HTTP $http_code)"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Next steps"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "To trigger a new sync for AccuWeather:"
echo "  curl -X POST \\"
echo "    $BASE_URL/admin/api/sync/trigger/$TENANT_ID \\"
echo "    -H 'X-API-Key: \$TENANT_MGMT_API_KEY' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"sync_type\": \"full\", \"force\": true}'"
echo ""
echo "To reset a stuck sync:"
echo "  ./scripts/reset_stuck_sync.sh $TENANT_ID"
echo ""
