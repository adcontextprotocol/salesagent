# Admin UI Guide

## Overview

The AdCP:Buy Server includes a web-based admin interface for managing tenants, viewing configuration, and accessing API tokens.

## Access the Admin UI

### With Docker Compose

When you start the services:

```bash
docker-compose up -d
```

The admin UI is available at: **http://localhost:8081**

Default login password: `admin`

### Running Standalone

```bash
# Set password (optional)
export ADMIN_UI_PASSWORD=your-secure-password

# Run the admin UI
python admin_ui.py

# Access at http://localhost:8081
```

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

### 4. API Tokens Tab

The most important section! Shows:
- **Admin Token** - For admin operations
- **Principal Tokens** - For each advertiser
- **Example API calls** - Copy-paste ready

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

### Step 4: Test API Access

```bash
# Use the admin token from the UI
export ADMIN_TOKEN="your-admin-token-from-ui"

# Test API
curl -H "x-adcp-auth: $ADMIN_TOKEN" \
     http://localhost:8080/principals/summary
```

### Step 5: Create Media Buy

Use one of the advertiser tokens:

```bash
# Use Acme Corp token from UI
export ACME_TOKEN="acme_corp_token"

# Create a media buy
curl -X POST \
  -H "x-adcp-auth: $ACME_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_ids": ["prod_1"],
    "total_budget": 5000,
    "flight_start_date": "2024-02-01",
    "flight_end_date": "2024-02-28"
  }' \
  http://localhost:8080/tools/create_media_buy
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