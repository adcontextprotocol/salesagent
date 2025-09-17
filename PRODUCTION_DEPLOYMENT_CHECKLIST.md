# Production Deployment Checklist

## Pre-Deployment Verification

### ✅ **1. Database & Tenant Setup**
```bash
# Run production setup verification
fly ssh console --app adcp-sales-agent --command "python scripts/production_setup.py"

# Expected output:
# ✅ Scribd: X principals, Y products
# ✅ Wonderstruck: X principals, Y products
# ✅ Production setup complete!
```

### ✅ **2. Code Quality & Tests**
```bash
# Run all tests locally first
uv run pytest tests/unit/ -x
uv run pytest tests/integration/ -x
uv run pytest tests/e2e/test_adcp_full_lifecycle.py -v

# Run pre-commit hooks
pre-commit run --all-files

# Check no hardcoded localhost in templates
grep -r "localhost:8080" templates/
# Should find no results after our fixes
```

### ✅ **3. Environment Configuration**
```bash
# Check required secrets are set
fly secrets list --app adcp-sales-agent

# Required secrets:
# - GEMINI_API_KEY
# - GAM_OAUTH_CLIENT_ID
# - GAM_OAUTH_CLIENT_SECRET
# - SUPER_ADMIN_EMAILS
```

### ✅ **4. DNS Setup (If Adding Custom Domain)**
```bash
# Verify DNS configuration
./scripts/verify_dns.sh

# Set up certificates (if DNS is ready)
fly certs create "sales-agent.scope3.com" --app adcp-sales-agent
fly certs create "*.sales-agent.scope3.com" --app adcp-sales-agent
```

## Deployment Process

### ✅ **5. Deploy to Production**
```bash
# Deploy latest code
fly deploy --app adcp-sales-agent

# Monitor deployment
fly logs --app adcp-sales-agent

# Check health
fly status --app adcp-sales-agent
```

### ✅ **6. Post-Deployment Verification**
```bash
# Basic health checks
curl https://adcp-sales-agent.fly.dev/health
curl https://adcp-sales-agent.fly.dev/admin/health

# Test tenant access (get tokens from production_setup.py output)
curl -H "x-adcp-auth: SCRIBD_TOKEN" -H "x-adcp-tenant: scribd" \
     https://adcp-sales-agent.fly.dev/mcp/tools/get_products

curl -H "x-adcp-auth: WONDERSTRUCK_TOKEN" -H "x-adcp-tenant: wonderstruck" \
     https://adcp-sales-agent.fly.dev/mcp/tools/get_products
```

### ✅ **7. Admin UI Verification**
```bash
# Test admin interface
open https://adcp-sales-agent.fly.dev/admin

# Verify tenant list shows correct ports/URLs:
# - Scribd: should show correct URL (not localhost:8080)
# - Wonderstruck: should show correct URL (not localhost:8080)
# - Default: should show correct URL (not localhost:8080)
```

## Regression Test Suite

### ✅ **8. Critical Path Tests**
Run these tests against production to ensure no regressions:

```bash
# Full lifecycle test with real production data
pytest tests/e2e/test_adcp_full_lifecycle.py --server-url=https://adcp-sales-agent.fly.dev

# A2A protocol compliance
pytest tests/e2e/test_a2a_adcp_compliance.py --server-url=https://adcp-sales-agent.fly.dev/a2a

# Schema compliance
pytest tests/e2e/test_adcp_schema_compliance.py --server-url=https://adcp-sales-agent.fly.dev
```

### ✅ **9. Tenant-Specific Tests**
```bash
# Test Scribd tenant
ADCP_AUTH_TOKEN=SCRIBD_TOKEN \
ADCP_TENANT_ID=scribd \
pytest tests/integration/test_mcp_protocol.py

# Test Wonderstruck tenant
ADCP_AUTH_TOKEN=WONDERSTRUCK_TOKEN \
ADCP_TENANT_ID=wonderstruck \
pytest tests/integration/test_mcp_protocol.py
```

### ✅ **10. UI Regression Tests**
```bash
# Test admin UI pages
pytest tests/ui/ --headless --base-url=https://adcp-sales-agent.fly.dev

# Manual checks:
# - Tenant list shows correct URLs
# - MCP endpoint URLs are correct in tenant settings
# - Python client examples use correct headers
```

## Rollback Plan

### 🚨 **If Issues Found**
```bash
# Quick rollback to previous deployment
fly releases --app adcp-sales-agent
fly releases rollback --app adcp-sales-agent v<PREVIOUS_VERSION>

# Monitor rollback
fly logs --app adcp-sales-agent
fly status --app adcp-sales-agent
```

### 🚨 **Database Issues**
```bash
# If database issues, run cleanup
fly ssh console --app adcp-sales-agent --command "python scripts/db_cleanup.py"

# Verify tenant data integrity
fly ssh console --app adcp-sales-agent --command "python scripts/production_setup.py"
```

## Success Criteria

### ✅ **Deployment Complete When:**

1. **Health Checks Pass**
   - `/health` returns 200
   - `/admin/health` returns 200
   - Database connections working

2. **Tenant Access Works**
   - Scribd tenant: Products returned via API
   - Wonderstruck tenant: Products returned via API
   - Default tenant: Still accessible

3. **Admin UI Functional**
   - Tenant list displays correct URLs (no localhost:8080)
   - Settings pages show proper MCP endpoints
   - All tenant management functions work

4. **No Regressions**
   - All E2E tests pass
   - Schema validation passes
   - A2A protocol compliance maintained

5. **DNS/Certificates (If Applicable)**
   - Custom domain resolves correctly
   - SSL certificates active
   - Subdomain routing functional

## Production URLs

### Current URLs (Path-based routing):
```
Base URL: https://adcp-sales-agent.fly.dev

Scribd MCP:       https://adcp-sales-agent.fly.dev/mcp/ + x-adcp-tenant: scribd
Wonderstruck MCP: https://adcp-sales-agent.fly.dev/mcp/ + x-adcp-tenant: wonderstruck
Default MCP:      https://adcp-sales-agent.fly.dev/mcp/ + x-adcp-tenant: default

Admin UI:         https://adcp-sales-agent.fly.dev/admin
A2A Endpoint:     https://adcp-sales-agent.fly.dev/a2a
```

### Future URLs (With custom domain):
```
Base URL: https://sales-agent.scope3.com

Scribd MCP:       https://scribd.sales-agent.scope3.com/mcp/
Wonderstruck MCP: https://wonderstruck.sales-agent.scope3.com/mcp/
Default MCP:      https://default.sales-agent.scope3.com/mcp/

Admin UI:         https://sales-agent.scope3.com/admin
A2A Endpoint:     https://sales-agent.scope3.com/a2a
```

---

**Remember**: Always test the deployment process in a staging environment first when possible.
