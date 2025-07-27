# Fly.io Deployment Guide for AdCP Sales Agent

This guide explains how to deploy the AdCP Sales Agent to Fly.io with proper ad server configuration.

## Overview

The AdCP Sales Agent connects publishers' ad inventory to AI-driven buyers. Each deployment:
- Connects to **one** upstream ad server (GAM, Triton, Kevel, etc.)
- Manages principals (buyers) through the database
- Requires only ad server credentials as secrets

## Prerequisites

1. Install Fly CLI:
```bash
curl -L https://fly.io/install.sh | sh
```

2. Sign up/login to Fly.io:
```bash
fly auth login
```

## Initial Setup

1. Create a new Fly app:
```bash
fly apps create adcp-sales-agent
```

2. Configure your ad server credentials:

### For Google Ad Manager (GAM)

```bash
# Set your GAM network code
fly secrets set GAM_NETWORK_CODE="123456789" --app adcp-sales-agent

# Set your service account credentials (as JSON string)
fly secrets set GAM_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"..."}' --app adcp-sales-agent

# Configure adapter
fly secrets set AD_SERVER_ADAPTER="gam" --app adcp-sales-agent
```

### For Triton Digital

```bash
# Set Triton API credentials
fly secrets set AD_SERVER_ADAPTER="triton_digital" --app adcp-sales-agent
fly secrets set AD_SERVER_BASE_URL="https://tap-api.tritondigital.com/v1" --app adcp-sales-agent
fly secrets set AD_SERVER_AUTH_TOKEN="your-triton-api-token" --app adcp-sales-agent
```

### For Mock/Development

```bash
# Use mock adapter (default)
fly secrets set AD_SERVER_ADAPTER="mock" --app adcp-sales-agent
```

### Optional: Gemini API (for AI features)

```bash
fly secrets set GEMINI_API_KEY="your-gemini-api-key" --app adcp-sales-agent
```

## Principal Management

Principals (buyers) are managed through the database, not environment variables:

1. **Development**: Sample principals are included (purina, acme_corp)
2. **Production**: Use the manage_auth.py script or SQL to add principals

### Adding Principals Before Deployment

Create a SQL script to initialize your principals:

```sql
-- init_principals.sql
INSERT INTO principals (principal_id, name, platform_mappings, access_token) VALUES 
('your_buyer', 'Your Buyer Name', '{"gam_advertiser_id": 12345}', 'secure-token-here');
```

Then update your Dockerfile to run this script:
```dockerfile
COPY init_principals.sql .
RUN uv run python -c "import sqlite3; conn = sqlite3.connect('adcp.db'); conn.executescript(open('init_principals.sql').read()); conn.close()"
```

### Managing Principals After Deployment

SSH into your container:
```bash
fly ssh console --app adcp-sales-agent
```

Use the manage_auth.py script:
```bash
# List principals
./manage_auth.py list

# Add a new principal
./manage_auth.py create buyer_id --name "Buyer Name"
```

## Deployment

Deploy the application:
```bash
fly deploy --app adcp-sales-agent
```

Check deployment status:
```bash
fly status --app adcp-sales-agent
```

View logs:
```bash
fly logs --app adcp-sales-agent
```

## Testing the Deployment

1. Get your app URL:
```bash
fly info --app adcp-sales-agent
# Look for the hostname, e.g., adcp-sales-agent.fly.dev
```

2. Test with the MCP client:
```bash
# Use a valid token from your principals table
./client_mcp.py --server https://adcp-sales-agent.fly.dev/mcp/ --token "your-principal-token" --test
```

## Environment Variables Reference

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `AD_SERVER_ADAPTER` | Ad server to connect to | Yes | `gam`, `triton_digital`, `kevel`, `mock` |
| `GAM_NETWORK_CODE` | GAM network code | If GAM | `123456789` |
| `GAM_SERVICE_ACCOUNT_JSON` | GAM service account credentials | If GAM | JSON string |
| `AD_SERVER_BASE_URL` | Base URL for ad server API | If Triton/Kevel | `https://api.example.com` |
| `AD_SERVER_AUTH_TOKEN` | Auth token for ad server | If Triton/Kevel | `token-123` |
| `GEMINI_API_KEY` | Google Gemini API key | No | `AIza...` |

## Architecture Notes

1. **One Ad Server per Agent**: Each deployment connects to exactly one ad server
2. **Database for Principals**: All buyer credentials stored in SQLite database
3. **Platform Mappings**: Each principal has adapter-specific IDs (e.g., GAM advertiser ID)

## Scaling

The app is configured with:
- 1GB RAM (sufficient for most workloads)
- Shared CPU
- Auto-stop when idle
- Auto-start on request

To scale up:
```bash
fly scale memory 2048 --app adcp-sales-agent
fly scale count 2 --app adcp-sales-agent
```

## Monitoring

View metrics:
```bash
fly dashboard metrics --app adcp-sales-agent
```

SSH into the container:
```bash
fly ssh console --app adcp-sales-agent
```

## Troubleshooting

1. **Authentication errors**: Ensure the token in `x-adcp-auth` header exists in principals table

2. **Ad server connection issues**: 
   - Check credentials are correctly set with `fly secrets list`
   - Verify network connectivity to ad server
   - Check logs for detailed error messages

3. **Database issues**: The SQLite database is ephemeral. For production:
   - Use Fly Volumes for persistence
   - Or migrate to PostgreSQL

4. **Memory issues**: If the app crashes, scale up memory:
   ```bash
   fly scale memory 2048 --app adcp-sales-agent
   ```

## Security Considerations

1. **Principal Tokens**: Generate strong, unique tokens for each buyer
2. **Ad Server Credentials**: Keep service account keys and API tokens secure
3. **HTTPS**: Always use HTTPS in production (Fly.io enforces this)
4. **Database**: Consider encrypting sensitive data in the database

## Updating

To update the deployment:

1. Make code changes
2. Deploy:
   ```bash
   fly deploy --app adcp-sales-agent
   ```

To update secrets:
```bash
fly secrets set VARIABLE_NAME="new-value" --app adcp-sales-agent
```

## Production Checklist

- [ ] Ad server credentials configured
- [ ] Production principals added to database
- [ ] Strong authentication tokens generated
- [ ] Appropriate memory/CPU allocated
- [ ] Monitoring configured
- [ ] Backup strategy for database (if using volumes)