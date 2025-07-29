# Admin UI Guide

## Overview

The AdCP Sales Agent includes a web-based admin interface for managing tenants, viewing configuration, and accessing API tokens. The admin UI supports two authentication methods:

1. **Google OAuth (Recommended)**: Secure authentication with email-based authorization
2. **Password-based (Legacy)**: Simple password authentication for development

## Access the Admin UI

### Option 1: Google OAuth (Recommended)

Uses Google Sign-In for secure, email-based authentication:

```bash
# Configure super admin access
export SUPER_ADMIN_EMAILS="admin@example.com,cto@example.com"
# OR use domain-based access
export SUPER_ADMIN_DOMAINS="example.com"

# Run the OAuth admin UI (port 8001)
python admin_ui_oauth.py

# Access at http://localhost:8001
```

See [Google OAuth Setup](google-oauth-setup.md) for detailed configuration.

### Option 2: Password-based (Legacy)

#### With Docker Compose

When you start the services:

```bash
docker-compose up -d
```

The admin UI is available at: **http://localhost:8081**

Default login: username `admin`, password `admin`

#### Running Standalone

```bash
# Set password (optional)
export ADMIN_UI_PASSWORD=your-secure-password

# Run the admin UI
python admin_ui.py

# Access at http://localhost:8081
```

### Multi-tenant Authentication

Both authentication methods support multi-tenant access:
- **Super Admins**: Can manage all tenants
- **Tenant Admins**: Can only manage their own tenant

## Features

### 1. Tenant Dashboard

The main page shows all tenants with:
- Tenant name and ID
- Subdomain and access URL
- Billing plan and status
- Quick access to management

![Tenant List](tenant-list.png)

### 2. Create New Tenant

Easy form to create tenants:
- Set name and subdomain
- Choose ad server adapter (Mock, GAM, Kevel)
- Configure features and limits
- Auto-generates secure tokens

### 3. Tenant Management

For each tenant, you can:
- **View/Edit Configuration** - JSON editor for advanced settings
- **See Principals** - List of advertisers and admins
- **View Products** - Available ad inventory
- **Access Tokens** - Copy tokens for API access
- **Operations Dashboard** - Monitor media buys, tasks, and audit logs

### 4. API Tokens Tab

The most important section! Shows:
- **Admin Token** - For admin operations
- **Principal Tokens** - For each advertiser
- **Example API calls** - Copy-paste ready

### 5. Operations Dashboard

Real-time monitoring and management:
- **Summary Cards** - Active media buys, total spend, pending tasks
- **Media Buys Tab** - List all campaigns with status filtering
- **Tasks Tab** - View and manage manual approval tasks
- **Audit Logs Tab** - Complete audit trail with security alerts
- **Live Filtering** - Filter by status without page reloads
- **Database Persistence** - All data stored persistently

## Workflow Example

### Step 1: Access Admin UI

```bash
# Start everything
docker-compose up -d

# Open browser
open http://localhost:8081

# Login with password: admin
```

### Step 2: View Default Tenant

Click on "Default Publisher" to see:
- Configuration
- Admin token
- Sample advertiser tokens

### Step 3: Copy Admin Token

Go to the "API Tokens" tab and copy the admin token.

### Step 4: Test MCP Access

Use the MCP command-line client to test access:

```bash
# Use the admin token from the UI
export ADMIN_TOKEN="your-admin-token-from-ui"

# Test with the MCP client
python client_mcp.py --token "$ADMIN_TOKEN" --test
```

### Step 5: Create Media Buy

Use one of the advertiser tokens with the MCP client:

```python
# Using Python MCP client
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Use Acme Corp token from UI
headers = {"x-adcp-auth": "acme_corp_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)

# Create a media buy
async with client:
    result = await client.tools.create_media_buy(
        product_ids=["prod_1"],
        total_budget=5000.0,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28"
    )
    print(f"Created media buy: {result.media_buy_id}")
```

Or create a simple test script:

```bash
# Save your token
export ACME_TOKEN="acme_corp_token"  # Get this from the Admin UI

# Create a test script
cat > test_buy.py << EOF
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
import os

async def main():
    token = os.environ.get('ACME_TOKEN', '')
    headers = {"x-adcp-auth": token}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        # Create a media buy
        result = await client.tools.create_media_buy(
            product_ids=["prod_1"],
            total_budget=5000.0,
            flight_start_date="2025-02-01", 
            flight_end_date="2025-02-28"
        )
        print(f"Created media buy: {result.media_buy_id}")

asyncio.run(main())
EOF

# Run it
python test_buy.py
```

You can also run the full simulation with your token:

```bash
# With custom token
python simulation_full.py http://localhost:8080 --token "acme_corp_token" --principal "acme_corp"

# Or use default demo tokens (purina_token)
python simulation_full.py http://localhost:8080
```

## Creating Additional Tenants

### Via UI

1. Click "Create Tenant"
2. Fill in:
   - Name: "Sports Publisher"
   - Subdomain: "sports"
   - Adapter: Mock (for testing)
3. Submit

### Via Command Line

```bash
docker exec -it adcp-server python setup_tenant.py "Sports Publisher" \
  --subdomain sports \
  --adapter mock
```

## Multi-Tenant Access

Each tenant has its own subdomain:

- Default: `http://localhost:8080`
- Sports: `http://sports.localhost:8080`
- News: `http://news.localhost:8080`

**Note**: Subdomain routing may require `/etc/hosts` entries:
```
127.0.0.1 sports.localhost
127.0.0.1 news.localhost
```

## Security

### Change Admin Password

Set environment variable before starting:

```bash
export ADMIN_UI_PASSWORD=very-secure-password
docker-compose up -d
```

### Production Deployment

1. Use strong admin password
2. Enable HTTPS with reverse proxy
3. Restrict access by IP if needed
4. Use PostgreSQL (not SQLite)

## Troubleshooting

### Can't Access Admin UI

```bash
# Check if running
docker ps | grep admin-ui

# Check logs
docker-compose logs admin-ui

# Ensure port 8081 is not in use
lsof -i :8081
```

### Login Failed

- Default password is `admin`
- Check `ADMIN_UI_PASSWORD` env var
- Clear browser cookies

### Database Connection Error

```bash
# Check database is running
docker-compose ps postgres

# Test connection
docker-compose exec admin-ui python -c "
from db_config import get_db_connection
conn = get_db_connection()
print('Connected!')
"
```

## Next Steps

1. **Explore the API**: Use tokens from the UI to test all endpoints
2. **Create Test Campaigns**: Try different targeting and creative options
3. **Monitor Logs**: Check `/audit_logs` for all operations
4. **Customize Tenants**: Edit JSON config for advanced features