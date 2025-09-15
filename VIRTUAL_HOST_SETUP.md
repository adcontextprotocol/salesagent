# Virtual Host Setup with Approximated.app

This guide explains how to set up custom virtual hosts for tenants using Approximated.app.

## ⚠️ **CRITICAL: Nginx Configuration Required**

**Virtual host routing will NOT work without updating the nginx configuration first!**

The current production nginx config intercepts root requests with a redirect before FastMCP can process virtual host headers. You MUST apply the nginx configuration changes in Step 1 below before virtual hosts will function.

## Overview

Virtual hosts allow tenants to access their AdCP Sales Agent through custom domains (e.g., `ad-sales.wonderstruck.org`) instead of using subdomains or tenant IDs. This provides a more professional, branded experience.

## Architecture

1. **Approximated.app** receives requests for your custom domain
2. **Apx-Incoming-Host header** is added containing the original hostname
3. **Nginx** forwards the request with the header to FastMCP (instead of redirecting)
4. **FastMCP** routes requests to the correct tenant based on the header
5. **Landing page** displays tenant-specific branding and API endpoints

## Setup Process

### 1. **FIRST: Update Nginx Configuration**

**Required before any other setup steps!**

The nginx configuration has been updated in this PR, but you need to restart nginx in production for the changes to take effect.

**Changes Made:**
- `config/nginx/nginx.conf` - Updated root handler to proxy to FastMCP instead of redirecting
- `fly/nginx.conf` - Updated root handler to proxy to MCP server instead of redirecting
- Both configs now forward the `Apx-Incoming-Host` header to FastMCP

**To Apply Changes in Production:**

1. **Fly.io Deployment:**
   ```bash
   fly deploy --app adcp-sales-agent
   ```
   The new nginx config will be deployed automatically.

2. **Manual Restart (if needed):**
   ```bash
   fly ssh console --app adcp-sales-agent
   # Inside the container:
   supervisorctl restart nginx
   ```

3. **Verify Configuration:**
   ```bash
   # Test that nginx no longer redirects root
   curl -I https://adcp-sales-agent.fly.dev/
   # Should get 200 OK, not 302 redirect

   # Test with virtual host header
   curl -H "Apx-Incoming-Host: test.com" https://adcp-sales-agent.fly.dev/
   # Should show FastMCP response, not nginx redirect
   ```

### 2. Configure Approximated.app

1. Sign up at https://approximated.app
2. Follow their integration guide to:
   - Point your custom domain to their service
   - Configure forwarding to your AdCP Sales Agent server
   - Ensure the `Apx-Incoming-Host` header is included

### 2. Configure Tenant in AdCP Admin UI

1. Access the Admin UI (typically at `http://your-server:8001/admin/`)
2. Navigate to the tenant's settings
3. Go to "General Settings"
4. Enter the virtual host domain in the "Virtual Host" field
5. Save the settings

### 3. Test the Configuration

Test with curl to verify the routing works:

```bash
curl -H "Apx-Incoming-Host: ad-sales.wonderstruck.org" http://localhost:8080/
```

Expected response: A branded landing page showing the tenant's name and API endpoints.

## API Endpoints with Virtual Hosts

When accessing through a virtual host, all standard endpoints work:

- **Landing Page**: `https://ad-sales.wonderstruck.org/`
- **MCP Endpoint**: `https://ad-sales.wonderstruck.org/mcp`
- **A2A Endpoint**: `https://ad-sales.wonderstruck.org/a2a`
- **Admin Dashboard**: `https://ad-sales.wonderstruck.org/admin/`

## Virtual Host Validation

The system validates virtual host entries to ensure they're properly formatted:

✅ **Valid formats:**
- `ad-sales.wonderstruck.org`
- `api.publisher.com`
- `test123.example.co.uk`
- `valid-host_123.example.org`

❌ **Invalid formats:**
- `invalid..domain` (consecutive dots)
- `.starting-dot.com` (starts with dot)
- `ending-dot.com.` (ends with dot)
- `special@characters.com` (special characters)

## Database Schema

The virtual host feature adds a `virtual_host` field to the `tenants` table:

```sql
ALTER TABLE tenants ADD COLUMN virtual_host TEXT;
CREATE UNIQUE INDEX ix_tenants_virtual_host ON tenants(virtual_host);
```

## Implementation Details

### Header Processing

The system checks for virtual host routing in this order:

1. **Apx-Incoming-Host** header (Approximated.app virtual hosts) - **Priority**
2. **x-adcp-tenant** header (custom middleware routing)
3. **Host** header subdomain extraction (legacy subdomain routing)

### Landing Page

When accessed through a virtual host, the root path (`/`) shows:

- Tenant-specific branding
- API endpoint URLs with the virtual host domain
- Links to admin dashboard and documentation
- Professional, clean design

### Authentication

Virtual host routing works with all existing authentication mechanisms:

- MCP clients use `x-adcp-auth` header as usual
- Admin UI uses Google OAuth as usual
- All existing tokens and principals work unchanged

## Troubleshooting

### Virtual Host Not Working

1. **Check Approximated.app configuration**
   - Verify domain is pointed correctly
   - Confirm `Apx-Incoming-Host` header is being sent

2. **Check tenant configuration**
   - Verify virtual host is saved in admin UI
   - Check for typos in domain name
   - Ensure no duplicate virtual hosts exist

3. **Test header forwarding**
   ```bash
   # Test locally with manual header
   curl -H "Apx-Incoming-Host: your-domain.com" http://localhost:8080/
   ```

### Database Issues

If migration fails:
```bash
# Run migration manually
uv run python scripts/ops/migrate.py
```

### Landing Page Not Showing

1. Check that `ADCP_UNIFIED_MODE` environment variable is set
2. Verify the virtual host header is being received
3. Check server logs for any errors in tenant lookup

## Security Considerations

- Virtual hosts are validated to prevent injection attacks
- Unique constraint prevents domain hijacking between tenants
- All existing security measures (authentication, authorization) apply unchanged

## Example Configuration

For a tenant named "Wonderstruck Media" with domain `ad-sales.wonderstruck.org`:

1. **Approximated.app**: Configure `ad-sales.wonderstruck.org` → your AdCP server
2. **Admin UI**: Set Virtual Host to `ad-sales.wonderstruck.org`
3. **Client access**: Use `https://ad-sales.wonderstruck.org/mcp` for MCP clients

The tenant will see a branded landing page and can share professional-looking API endpoints with their advertisers.
