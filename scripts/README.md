# AdCP Scripts

This directory contains utility scripts for testing and managing the AdCP Sales Agent.

## Sync API Testing

### test_sync_api.py
A comprehensive Python test script that demonstrates all sync API functionality:
- Retrieves the superadmin API key
- Lists all GAM-enabled tenants
- Triggers a sync
- Monitors sync progress
- Shows sync history

```bash
# Run the test (make sure the server is running first)
./test_sync_api.py

# Or with Python directly
python test_sync_api.py
```

### sync_api_curl_examples.sh
Simple curl-based examples for quick API testing:
- Shows exact curl commands
- Can be used for debugging or integration testing
- Requires `jq` for JSON formatting

```bash
# Run the examples
./sync_api_curl_examples.sh

# Or source it to get the commands
source sync_api_curl_examples.sh
```

## Cron Job Scripts

### sync_all_tenants.py
Production script designed to be run by cron:
- Syncs all active GAM tenants
- Uses the superadmin API key for authentication
- Logs results and handles errors gracefully

```bash
# Run manually
python sync_all_tenants.py

# Typically run by cron every 6 hours
# See ../crontab for schedule
```

## Other Utilities

### update_oauth_redirect_uri.py
Updates Google OAuth redirect URIs for different deployment environments.

### validate_column_lengths.py
Validates database column lengths to prevent truncation errors.

### check_schema_references.py
Checks for references to removed database columns.

## Testing Without UI

The sync API allows complete testing without UI interaction:

```python
# Python example
import requests

api_key = "your-superadmin-api-key"
tenant_id = "your-tenant-id"

# Trigger sync
response = requests.post(
    f"http://localhost:8001/api/v1/sync/trigger/{tenant_id}",
    headers={"X-API-Key": api_key},
    json={"sync_type": "incremental"}
)

# Check status
status = requests.get(
    f"http://localhost:8001/api/v1/sync/status/{tenant_id}",
    headers={"X-API-Key": api_key}
)
```

This approach enables:
- Automated testing in CI/CD
- Debugging without manual UI clicks
- Performance testing
- Integration with external systems
