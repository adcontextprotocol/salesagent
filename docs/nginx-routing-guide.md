# Nginx Routing Guide

Complete reference for how requests are routed through nginx to our backend services.

## Architecture Overview

```
┌─── Main Domain (Direct) ──────┐   ┌─── Tenant Subdomains (Direct) ───┐
│  sales-agent.scope3.com        │   │  wonderstruck.sales-agent.scope3  │
│  Host: sales-agent.scope3.com  │   │  Host: wonderstruck.sales-agent.. │
│  Apx-Incoming-Host: (not set)  │   │  Apx-Incoming-Host: (not set)     │
└────────────────┬───────────────┘   └────────────────┬──────────────────┘
                 │                                     │
                 └──────────► [Fly.io nginx] ◄─────────┘
                                      │
                                      └─► [Backend Services]


┌─── External Domains (Via Approximated) ────┐
│  test-agent.adcontextprotocol.org           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
         [Approximated CDN]
                  │
           Sets headers:
           - Host: sales-agent.scope3.com
           - Apx-Incoming-Host: test-agent.adcontextprotocol.org
                  │
                  ▼
         [Fly.io nginx] → [Backend Services]
```

**Key Insights**:
- **Main domain** (`sales-agent.scope3.com`) goes **directly to Fly** - Host header is `sales-agent.scope3.com`, no `Apx-Incoming-Host`
- **Tenant subdomains** (`*.sales-agent.scope3.com`) go **directly to Fly** - Host header has full subdomain, no `Apx-Incoming-Host`
- **ONLY external domains** route through **Approximated** - Host is rewritten to `sales-agent.scope3.com` and `Apx-Incoming-Host` is set to original domain
- Nginx routing logic: If `Apx-Incoming-Host` is NOT set → use `Host` header. If `Apx-Incoming-Host` IS set → it's an external domain

## Backend Services

| Service | Port | Purpose |
|---------|------|---------|
| Admin UI | 8001 | Web interface, signup, dashboard |
| MCP Server | 8080 | Model Context Protocol (AI agents) |
| A2A Server | 8091 | Agent-to-Agent protocol |

## Domain Types

### 1. Main Domain
- **Domain**: `sales-agent.scope3.com`
- **Purpose**: Publisher self-service signup
- **Traffic Path**: **Direct to Fly** (does NOT go through Approximated)
- **Headers**: `Host: sales-agent.scope3.com`, no `Apx-Incoming-Host` header

### 2. Tenant Subdomains
- **Pattern**: `<tenant>.sales-agent.scope3.com`
- **Examples**: `wonderstruck.sales-agent.scope3.com`
- **Purpose**: Tenant-specific access (MCP/A2A endpoints)
- **Traffic Path**: **Direct to Fly** (does NOT go through Approximated)
- **Headers**: `Host: wonderstruck.sales-agent.scope3.com` (subdomain preserved)

### 3. External Virtual Hosts (White-Labeled Agent Access)
- **Pattern**: `<any-domain-not-ending-in>.sales-agent.scope3.com`
- **Examples**:
  - `test-agent.adcontextprotocol.org`
  - `custom-domain.example.com`
- **Purpose**: White-labeled **agent access** (MCP/A2A) - **admin uses subdomain**
- **Traffic Path**: Through Approximated (which sets `Apx-Incoming-Host` header)
- **Functionality**: Agent endpoints (MCP, A2A, landing page) - **no admin UI**
- **Mapping**: External domain maps to tenant ID (configured in database)
- **Admin Access**: Use subdomain `<tenant>.sales-agent.scope3.com/admin` (OAuth works there)

## Routing Decision Tree

```
Request arrives at nginx
  ↓
Check Apx-Incoming-Host header
  ↓
  ├─ Ends with .sales-agent.scope3.com?
  │   ├─ YES → Check if subdomain exists
  │   │   ├─ sales-agent.scope3.com (no subdomain)
  │   │   │   └─ Main domain routing
  │   │   └─ <tenant>.sales-agent.scope3.com
  │   │       └─ Tenant subdomain routing
  │   │
  │   └─ NO → External virtual host routing
```

## Detailed Routing Tables

### 1. Main Domain: `sales-agent.scope3.com`

**Shows**: Publisher self-service signup flow

| Path | Backend | Purpose | Response |
|------|---------|---------|----------|
| `/` | Admin UI `/signup` | Entry point | Signup page |
| `/signup` | Admin UI `/signup` | OAuth initiation | Google OAuth redirect |
| `/login` | Admin UI `/login` | Login page | Login form |
| `/auth/google/callback` | Admin UI | OAuth callback | Creates tenant, redirects to dashboard |
| `/admin/*` | Admin UI `/admin/*` | Authenticated admin | Requires login |
| `/mcp/*` | ❌ 404 | Not tenant-specific | Error |
| `/a2a/*` | ❌ 404 | Not tenant-specific | Error |
| `/health` | Admin UI `/health` | Health check | `{"status": "healthy"}` |

**Visual Flow**:
```
https://sales-agent.scope3.com/
  ↓ (nginx rewrites to /signup)
Admin UI renders signup page
  ↓ (user clicks "Sign up with Google")
/signup → Google OAuth
  ↓
/auth/google/callback
  ↓
Creates tenant in database
  ↓
302 Redirect → /admin/tenant/<tenant_id>
  ↓
Shows tenant dashboard
```

### 2. Tenant Subdomain: `<tenant>.sales-agent.scope3.com`

**Shows**: Tenant-specific MCP/A2A endpoints + admin access

| Path | Backend | Purpose | Auth Required |
|------|---------|---------|---------------|
| `/` | Admin UI `/` | Landing page | No |
| `/admin/*` | Admin UI `/admin/*` | Admin interface | Yes (OAuth) |
| `/mcp/` | MCP Server `:8080` | MCP protocol | Yes (`x-adcp-auth` header) |
| `/a2a/` | A2A Server `:8091` | A2A protocol | Yes (`Authorization` header) |
| `/.well-known/agent.json` | A2A Server | Agent discovery | No |
| `/health` | Admin UI `/health` | Health check | No |

**Visual Flow - MCP Request**:
```
https://wonderstruck.sales-agent.scope3.com/mcp/
Headers:
  Host: sales-agent.scope3.com
  Apx-Incoming-Host: wonderstruck.sales-agent.scope3.com
  x-adcp-auth: <principal-token>
  ↓
nginx extracts subdomain: "wonderstruck"
  ↓
Sets header: X-Tenant-Id: wonderstruck
  ↓
Proxies to: http://mcp_server:8080
  ↓
MCP server reads X-Tenant-Id header
  ↓
Resolves tenant + principal from token
  ↓
Returns MCP response for that tenant
```

**Visual Flow - A2A Request**:
```
https://wonderstruck.sales-agent.scope3.com/a2a/
Headers:
  Host: sales-agent.scope3.com
  Apx-Incoming-Host: wonderstruck.sales-agent.scope3.com
  Authorization: Bearer <token>
  ↓
nginx sets X-Tenant-Id: wonderstruck
  ↓
Proxies to: http://a2a_server:8091
  ↓
A2A server resolves tenant context
  ↓
Returns A2A response
```

**Visual Flow - Admin Access**:
```
https://wonderstruck.sales-agent.scope3.com/admin/products
  ↓
nginx proxies to Admin UI
  ↓
Admin UI checks session authentication
  ↓
If not authenticated:
  302 Redirect → /login
  ↓
After login:
  Shows products for "wonderstruck" tenant
```

### 3. External Virtual Host: `test-agent.adcontextprotocol.org`

**Shows**: White-labeled **agent access** - **admin UI NOT supported** (use subdomain)

| Path | Backend | Purpose | Response |
|------|---------|---------|----------|
| `/` | Admin UI `/` | Tenant landing page | Tenant's public landing page |
| `/admin/*` | ❌ Redirect | Not supported on external | 302 → `https://<tenant>.sales-agent.scope3.com/admin/*` |
| `/mcp/` | MCP Server `:8080` | MCP protocol | ✅ Works (auth required) |
| `/a2a/` | A2A Server `:8091` | A2A protocol | ✅ Works (auth required) |
| `/.well-known/agent.json` | A2A Server | Agent discovery | ✅ Works (public) |
| `/health` | Admin UI `/health` | Health check | ✅ Works |

**Visual Flow - Agent Access**:
```
https://test-agent.adcontextprotocol.org/mcp/
Headers:
  Host: sales-agent.scope3.com (rewritten by Approximated)
  Apx-Incoming-Host: test-agent.adcontextprotocol.org
  x-adcp-auth: <principal-token>
  ↓
nginx looks up tenant_id from domain mapping
  Example: test-agent.adcontextprotocol.org → "wonderstruck"
  ↓
Sets header: X-Tenant-Id: wonderstruck
  ↓
Proxies to: http://mcp_server:8080
  ↓
MCP server reads X-Tenant-Id header
  ↓
Resolves tenant + principal from token
  ↓
Returns MCP response for that tenant
  (SAME DATA as wonderstruck.sales-agent.scope3.com/mcp/)
```

**Visual Flow - Admin Redirect**:
```
https://test-agent.adcontextprotocol.org/admin/products
  ↓
nginx detects /admin/* on external domain
  ↓
302 Redirect → https://wonderstruck.sales-agent.scope3.com/admin/products
  ↓
User lands on subdomain where OAuth works properly
```

**Why admin is NOT supported on external domains**:
- **OAuth problem**: Callback goes to `sales-agent.scope3.com`, can't set cookies for external domain
- **Simple solution**: Admin UI only works on subdomain
- **User flow**: External domain redirects `/admin/*` to subdomain
- **Agent access**: Still works perfectly on external domain (header-based auth, no cookies)
- **Result**: Clean architecture, no cross-domain OAuth complexity

## Nginx Configuration Patterns

### Pattern 1: Domain Type Detection
```nginx
# Map to detect external domains
map $http_apx_incoming_host $is_external_domain {
    default 0;
    "~*^(?!.*\.sales-agent\.scope3\.com$).*$" 1;
}

# Route based on domain type
map $is_external_domain $backend_path {
    0 /signup;  # Main/subdomain → signup flow
    1 /;        # External → landing page
}
```

### Pattern 2: Subdomain Extraction
```nginx
# Extract subdomain from Apx-Incoming-Host
map $http_apx_incoming_host $extracted_subdomain {
    default "";
    "~*^(?<subdomain>[^.]+)\.sales-agent\.scope3\.com$" $subdomain;
}

# Set tenant ID header for backend services
proxy_set_header X-Tenant-Id $extracted_subdomain;
```

### Pattern 3: Path-Based Routing
```nginx
# Root path varies by domain type
location = / {
    proxy_pass http://admin_ui$backend_path;
}

# MCP endpoint (tenant subdomains only)
location /mcp/ {
    if ($extracted_subdomain = "") {
        return 404;  # No MCP on main domain
    }
    proxy_pass http://mcp_server:8080;
}

# A2A endpoint (tenant subdomains only)
location /a2a/ {
    if ($extracted_subdomain = "") {
        return 404;  # No A2A on main domain
    }
    proxy_pass http://a2a_server:8091;
}
```

## Security Boundaries

### Tenant Isolation
- Nginx extracts subdomain and sets `X-Tenant-Id` header
- Backend services validate tenant exists and token matches
- No cross-tenant data access possible

### External Domain Restrictions
- Cannot access `/admin/*` (admin interface)
- Cannot access `/mcp/` (no agent access)
- Cannot access `/a2a/` (no agent communication)
- Only shows marketing landing page

### Authentication
- **Admin UI**: Session-based (OAuth)
- **MCP**: Header-based (`x-adcp-auth: <token>`)
- **A2A**: Bearer token (`Authorization: Bearer <token>`)

## Common Issues & Solutions

### Issue 1: External domain shows login page instead of landing
**Symptom**: `test-agent.adcontextprotocol.org` shows `/login`

**Root Cause**: Nginx not detecting external domain correctly

**Fix**: Check `$is_external_domain` map logic
```nginx
map $http_apx_incoming_host $is_external_domain {
    default 0;
    "~*^(?!.*\.sales-agent\.scope3\.com$).*$" 1;
}
```

### Issue 2: Tenant subdomain can't access MCP
**Symptom**: `wonderstruck.sales-agent.scope3.com/mcp/` returns 404

**Root Cause**: Subdomain extraction failing or MCP location block misconfigured

**Fix**: Verify subdomain extraction:
```nginx
map $http_apx_incoming_host $extracted_subdomain {
    "~*^(?<subdomain>[^.]+)\.sales-agent\.scope3\.com$" $subdomain;
}
```

### Issue 3: Main domain redirects to itself infinitely
**Symptom**: `sales-agent.scope3.com/` → `/signup` → `/signup` → ...

**Root Cause**: Both `/` and `/signup` trying to redirect

**Fix**: Use `proxy_pass` with variable, not redirect:
```nginx
location = / {
    proxy_pass http://admin_ui$backend_path;  # Proxies to /signup
}
```

## Testing Checklist

### Main Domain (`sales-agent.scope3.com`)
- [ ] `/` → Shows signup page (not redirect loop)
- [ ] `/signup` → Initiates Google OAuth
- [ ] `/login` → Shows login form
- [ ] `/admin/` → Requires authentication
- [ ] `/mcp/` → Returns 404
- [ ] `/health` → Returns healthy

### Tenant Subdomain (`wonderstruck.sales-agent.scope3.com`)
- [ ] `/` → Shows landing page
- [ ] `/admin/` → Requires authentication, shows tenant dashboard
- [ ] `/mcp/` → Accepts MCP requests with auth
- [ ] `/a2a/` → Accepts A2A requests with auth
- [ ] `/.well-known/agent.json` → Returns agent card
- [ ] `/health` → Returns healthy

### External Domain (`test-agent.adcontextprotocol.org`)
- [ ] `/` → Shows marketing landing page
- [ ] `/signup` → Redirects to `sales-agent.scope3.com/signup`
- [ ] `/admin/` → Returns 403 or redirects away
- [ ] `/mcp/` → Returns 404
- [ ] `/a2a/` → Returns 404
- [ ] `/.well-known/agent.json` → Returns 404

## Debugging Commands

### Check what nginx sees
```bash
# SSH into Fly instance
fly ssh console -a adcp-sales-agent

# Check nginx logs
tail -f /var/log/nginx/access.log

# Check for specific domain
grep "test-agent.adcontextprotocol.org" /var/log/nginx/access.log
```

### Test locally (simulate Approximated headers)
```bash
# Main domain
curl -H "Host: sales-agent.scope3.com" \
     -H "Apx-Incoming-Host: sales-agent.scope3.com" \
     http://localhost:8001/

# Tenant subdomain
curl -H "Host: sales-agent.scope3.com" \
     -H "Apx-Incoming-Host: wonderstruck.sales-agent.scope3.com" \
     http://localhost:8001/

# External domain
curl -H "Host: sales-agent.scope3.com" \
     -H "Apx-Incoming-Host: test-agent.adcontextprotocol.org" \
     http://localhost:8001/
```

## Reference: Current Implementation Status

✅ **Implemented**:
- External domain detection via `Apx-Incoming-Host`
- Landing page routing for external domains
- Subdomain extraction for tenant routing
- Path-based routing to MCP/A2A services

⚠️ **Known Limitations**:
- Cannot test Approximated behavior locally (requires Fly deployment)
- OAuth callback URLs must match production domain
- Health check endpoints may need CORS headers

📋 **TODO** (if needed):
- Rate limiting per domain type
- Custom error pages per domain
- Logging/metrics per domain type
