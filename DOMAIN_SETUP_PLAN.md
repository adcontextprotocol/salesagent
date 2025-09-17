# Domain Setup Plan for Tenant-Specific Subdomain Support

## Current Status ✅

**Production App**: Working correctly at https://adcp-sales-agent.fly.dev/health (HTTP 200)
**SSL Certificates**: Ready for `*.sales-agent.scope3.com` and `sales-agent.scope3.com`
**Nginx Configuration**: Needs update for tenant-specific subdomain routing
**Health Checks**: Fly.io app is healthy and responding

## Next Steps Required

**Issue**: `sales-agent.scope3.com` is currently routing through Cloudflare (520 errors), not directly to Fly.io
**Solution**: Configure Cloudflare DNS to properly proxy to Fly.io or set up direct DNS routing

## Selected Domain: `sales-agent.scope3.com`

### Architecture Overview
**Tenant-Specific Subdomains**:
- `https://[tenant].sales-agent.scope3.com/mcp/` - Direct MCP access per tenant
- `https://[tenant].sales-agent.scope3.com/a2a/` - Direct A2A access per tenant
- `https://admin.sales-agent.scope3.com/` - Admin interface (service-specific)
- `https://sales-agent.scope3.com/` - Base domain (redirects to admin)

### Benefits
- ✅ **Direct tenant access**: No headers required for tenant identification
- ✅ **Clean tenant URLs**: Each tenant gets their own subdomain
- ✅ **Professional branding**: Uses established Scope3 domain
- ✅ **Tenant isolation**: Clear URL-level separation between tenants
- ✅ **Enterprise credibility**: .com domain with company branding
- ✅ **Zero additional cost**: Uses existing scope3.com infrastructure

### Tenant URL Examples (Current Database)
Based on existing tenant subdomains:
- `https://scribd.sales-agent.scope3.com/mcp/` - Scribd's MCP endpoint
- `https://wonderstruck.sales-agent.scope3.com/a2a/` - Wonderstruck's A2A endpoint
- `https://default.sales-agent.scope3.com/mcp/` - Default tenant's MCP endpoint
- `https://admin.sales-agent.scope3.com/` - Admin dashboard

### Client Integration Examples
```python
# Python MCP client for Scribd tenant
headers = {"x-adcp-auth": "scribd_token_here"}
transport = StreamableHttpTransport(
    url="https://scribd.sales-agent.scope3.com/mcp/",
    headers=headers
)

# A2A client for Wonderstruck tenant
response = requests.post(
    "https://wonderstruck.sales-agent.scope3.com/a2a/",
    headers={"Authorization": "Bearer wonderstruck_token"},
    json={"query": "List available products"}
)
```

### Previous Alternative Options (No Longer Needed)
1. `adcp-sales.dev` - Would require new domain purchase
2. `adcpsales.io` - Would require new domain purchase
3. `adcp-sales.com` - Would require new domain purchase

## Setup Process

### 1. DNS Configuration (scope3.com domain)
Add these DNS records to the existing scope3.com zone:
```bash
# DNS Records needed for service subdomains:
A     admin.sales-agent.scope3.com → 66.241.125.123    # Fly.io IPv4 - Admin UI
AAAA  admin.sales-agent.scope3.com → 2a09:8280:1::4:3c9b # Fly.io IPv6 - Admin UI
A     mcp.sales-agent.scope3.com   → 66.241.125.123    # Fly.io IPv4 - MCP Server
AAAA  mcp.sales-agent.scope3.com   → 2a09:8280:1::4:3c9b # Fly.io IPv6 - MCP Server
A     a2a.sales-agent.scope3.com   → 66.241.125.123    # Fly.io IPv4 - A2A Server
AAAA  a2a.sales-agent.scope3.com   → 2a09:8280:1::4:3c9b # Fly.io IPv6 - A2A Server

# Optional: Wildcard for future tenant subdomains
CNAME *.sales-agent.scope3.com     → adcp-sales-agent.fly.dev
```

### 2. Fly.io Certificate Setup
```bash
# Create certificates for service subdomains
fly certs create "admin.sales-agent.scope3.com" --app adcp-sales-agent
fly certs create "mcp.sales-agent.scope3.com" --app adcp-sales-agent
fly certs create "a2a.sales-agent.scope3.com" --app adcp-sales-agent

# Optional: Create wildcard certificate for tenant subdomains
fly certs create "*.sales-agent.scope3.com" --app adcp-sales-agent

# Add DNS validation records (provided by Fly.io) to scope3.com zone
# Example: _acme-challenge.admin.sales-agent.scope3.com → validation-string.acme.letsencrypt.org
```

### 3. Verify Setup
```bash
# Check certificate status
fly certs list --app adcp-sales-agent

# Test service endpoints
curl https://admin.sales-agent.scope3.com/health
curl https://mcp.sales-agent.scope3.com/health
curl https://a2a.sales-agent.scope3.com/health

# Test MCP with tenant header
curl -H "x-adcp-tenant: scribd" https://mcp.sales-agent.scope3.com/mcp/tools/get_products

# Test A2A with tenant header
curl -H "x-adcp-tenant: scribd" https://a2a.sales-agent.scope3.com/a2a
```

## Code Updates Required

### Environment Detection
Add service subdomain configuration to environment:
```bash
# .env / production secrets
SERVICE_DOMAIN=sales-agent.scope3.com
ENABLE_SERVICE_SUBDOMAINS=true
```

### Template Logic Enhancement
```jinja2
<!-- Admin interface URL -->
{% if custom_domain and enable_service_subdomains %}
    https://admin.{{ service_domain }}/
{% elif is_production %}
    https://adcp-sales-agent.fly.dev/admin/
{% else %}
    http://localhost:{{ admin_port }}/
{% endif %}

<!-- MCP endpoint URL -->
{% if tenant.virtual_host %}
    <!-- Virtual host takes priority -->
    https://{{ tenant.virtual_host }}/mcp/
{% elif custom_domain and enable_service_subdomains %}
    <!-- Service subdomain with tenant header -->
    https://mcp.{{ service_domain }}/mcp/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% elif is_production %}
    <!-- Fallback to path-based -->
    https://adcp-sales-agent.fly.dev/mcp/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% else %}
    <!-- Development -->
    http://localhost:{{ mcp_port }}/mcp/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% endif %}

<!-- A2A endpoint URL -->
{% if custom_domain and enable_service_subdomains %}
    https://a2a.{{ service_domain }}/a2a/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% elif is_production %}
    https://adcp-sales-agent.fly.dev/a2a/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% else %}
    http://localhost:{{ a2a_port }}/a2a/
    (use x-adcp-tenant: {{ tenant.subdomain }})
{% endif %}
```

### Routing Configuration
```python
# Add to Flask app configuration
from flask import request

@app.before_request
def handle_service_subdomains():
    """Route requests based on service subdomain."""
    host = request.headers.get('Host', '')

    if host.startswith('admin.sales-agent.scope3.com'):
        # Admin interface - no routing needed
        pass
    elif host.startswith('mcp.sales-agent.scope3.com'):
        # MCP requests - ensure they hit MCP endpoints
        pass
    elif host.startswith('a2a.sales-agent.scope3.com'):
        # A2A requests - ensure they hit A2A endpoints
        pass
```

## Migration Strategy

### Phase 1: Domain Setup (Admin Only)
1. Purchase and configure domain
2. Set up certificates
3. Test basic connectivity

### Phase 2: Dual Support
- Keep existing path-based routing
- Add subdomain routing as option
- Update templates to show both methods

### Phase 3: Gradual Migration
- New tenants get subdomain URLs by default
- Existing tenants can opt-in to subdomain URLs
- Maintain backward compatibility

## Benefits After Implementation

### For Tenants
```bash
# Before (Path-based)
curl -H "x-adcp-tenant: scribd" https://adcp-sales-agent.fly.dev/mcp/tools/get_products

# After (Service subdomain with Scope3 branding)
curl -H "x-adcp-tenant: scribd" https://mcp.sales-agent.scope3.com/mcp/tools/get_products
```

### For Users
- ✅ **Service separation**: Clear protocol boundaries with dedicated URLs
- ✅ **Cleaner URLs**: Professional subdomain structure
- ✅ **Better organization**: Admin, MCP, and A2A services clearly separated
- ✅ **Scope3 branding**: All services under sales-agent.scope3.com
- ✅ **Easier debugging**: Service-specific logs and monitoring

### For Development
- ✅ **Clear architecture**: Each protocol at its own subdomain
- ✅ **Better routing**: Service-specific routing and middleware
- ✅ **Improved monitoring**: Service-level metrics and health checks
- ✅ **Consistent dev/prod patterns**: Same subdomain structure locally and in production
- ✅ **Easier tenant isolation**: Service-specific tenant routing
- ✅ **Better logs/monitoring**: Service-specific log aggregation

## Cost Estimate
- Domain: **$0** (using existing scope3.com)
- DNS Management: **$0** (existing DNS provider)
- Certificates: **$0** (Let's Encrypt via Fly.io)
- **Total**: **FREE** 🎉

## Implementation Priority
- **High**: Improves user experience significantly
- **Medium**: Not blocking for current functionality
- **Low**: Path-based routing works fine as interim solution

The path-based approach we implemented is correct for now, but adding a custom domain would significantly improve the user experience and make tenant URLs much cleaner.
