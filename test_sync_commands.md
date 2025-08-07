# Test Sync Commands

## Test Scribd tenant specifically:
```bash
docker exec -it adcp-buy-server-adcp-server-1 python scripts/test_all_tenants_sync.py --tenant scribd
```

## Test all GAM tenants:
```bash
docker exec -it adcp-buy-server-adcp-server-1 python scripts/test_all_tenants_sync.py --all
```

## Quick check which tenants exist:
```bash
docker exec adcp-buy-server-adcp-server-1 sqlite3 adcp_local.db "SELECT t.tenant_id, t.name, t.subdomain, ac.adapter_type FROM tenants t LEFT JOIN adapter_config ac ON t.tenant_id = ac.tenant_id WHERE ac.adapter_type = 'google_ad_manager' ORDER BY t.name;"
```

## Trigger sync via curl for Scribd:
```bash
# Get the API key
API_KEY=$(docker exec adcp-buy-server-adcp-server-1 sqlite3 adcp_local.db "SELECT value FROM superadmin_config WHERE key='api_key';")

# Get Scribd tenant ID
TENANT_ID=$(docker exec adcp-buy-server-adcp-server-1 sqlite3 adcp_local.db "SELECT tenant_id FROM tenants WHERE LOWER(name) LIKE '%scribd%' OR LOWER(subdomain) LIKE '%scribd%' LIMIT 1;")

# Trigger sync
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "incremental"}' \
  "http://localhost:8001/api/v1/sync/trigger/$TENANT_ID"

# Check status
curl -X GET \
  -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/api/v1/sync/status/$TENANT_ID" | jq
```

## Run the original single-tenant test:
```bash
docker exec -it adcp-buy-server-adcp-server-1 python scripts/test_sync_api.py
```