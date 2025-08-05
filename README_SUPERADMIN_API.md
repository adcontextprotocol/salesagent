# Super Admin API for AdCP Sales Agent

## Overview

The Super Admin API provides programmatic access to manage tenants in the AdCP Sales Agent server. This API was designed specifically for integration with the Scope3 application to automate the provisioning of AdCP tenants when users set up their advertising integrations.

## Key Features

- **API Key Authentication**: Secure access via `X-Superadmin-API-Key` header
- **Full Tenant CRUD**: Create, read, update, and delete tenant configurations
- **GAM OAuth Integration**: Store and manage Google Ad Manager refresh tokens
- **Automated Provisioning**: Create fully configured tenants with a single API call
- **Multi-Adapter Support**: Works with Google Ad Manager, Kevel, Triton, and Mock adapters

## Quick Start

### 1. Initialize the API Key (One-time Setup)

First, initialize the super admin API key:

```bash
curl -X POST http://localhost:8001/api/v1/superadmin/init-api-key
```

Save the returned API key securely - it cannot be retrieved again!

### 2. Test the API

Run the test script to verify everything is working:

```bash
python test_superadmin_api.py
```

### 3. Create a Tenant

Example: Create a minimal GAM tenant (just refresh token):

```bash
curl -X POST http://localhost:8001/api/v1/superadmin/tenants \
  -H "X-Superadmin-API-Key: sk-your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sports Publisher",
    "subdomain": "sports",
    "ad_server": "google_ad_manager",
    "gam_refresh_token": "1//oauth-refresh-token"
  }'
```

The publisher can then configure the network code and other settings in the Admin UI.

## Integration Flow for Scope3

The typical integration flow is:

1. **User initiates setup** in Scope3 app
2. **OAuth flow** captures GAM credentials
3. **Create tenant** via Super Admin API
4. **Redirect user** to their provisioned AdCP admin UI

See `examples/scope3_integration.py` for a complete implementation example.

## Files Added

- `superadmin_api.py` - Flask blueprint with all API endpoints
- `test_superadmin_api.py` - Interactive test script
- `test_superadmin_api_unit.py` - Unit tests with pytest
- `docs/superadmin-api.md` - Complete API documentation
- `examples/scope3_integration.py` - Integration example for Scope3
- `alembic/versions/008_add_superadmin_api_key.py` - Database migration

## Security Considerations

1. **API Key Storage**: Store the super admin API key in environment variables or a secure vault
2. **HTTPS Only**: Always use HTTPS in production
3. **Rate Limiting**: Consider implementing rate limiting
4. **Audit Trail**: All operations are logged to the audit_logs table

## Testing

Run the unit tests:

```bash
uv run pytest test_superadmin_api_unit.py -v
```

Run the integration test:

```bash
python test_superadmin_api.py
```

## Environment Variables

For production deployment, set:

```bash
# In your Scope3 app
ADCP_SERVER_URL=https://adcp.example.com
ADCP_SUPERADMIN_API_KEY=sk-your-api-key-here
```

## Next Steps

1. Deploy the updated AdCP Sales Agent with this API
2. Implement the OAuth flow in Scope3 for GAM credentials
3. Use the `AdCPTenantManager` class from the examples in your integration
4. Set up monitoring for API usage and errors