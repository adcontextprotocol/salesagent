# Scope3 Dependency Removal Progress

## Objective
Remove all hardcoded Scope3 domain references from the codebase to make it vendor-neutral and configurable via environment variables.

## What We've Done

### 1. Created Domain Configuration Module ✅
**File**: `src/core/domain_config.py`

New centralized module provides:
- `get_base_domain()` - Base domain (e.g., example.com)
- `get_sales_agent_domain()` - Sales agent domain (e.g., sales-agent.example.com)
- `get_admin_domain()` - Admin domain (e.g., admin.sales-agent.example.com)
- `get_super_admin_domain()` - Super admin email domain
- `get_sales_agent_url()` - Full HTTPS URL
- `get_a2a_server_url()` - A2A server endpoint URL
- `get_mcp_server_url()` - MCP server endpoint URL
- `is_sales_agent_domain(host)` - Check if host is part of sales agent domain
- `extract_subdomain_from_host(host)` - Extract tenant subdomain
- `get_tenant_url(subdomain)` - Get full tenant URL
- `get_oauth_redirect_uri()` - OAuth callback URL
- `get_session_cookie_domain()` - Cookie domain for session sharing

### 2. Updated Environment Configuration ✅
**File**: `.env.example`

Added new environment variables:
```bash
BASE_DOMAIN=example.com
SALES_AGENT_DOMAIN=sales-agent.example.com
ADMIN_DOMAIN=admin.sales-agent.example.com
SUPER_ADMIN_DOMAIN=example.com
GOOGLE_OAUTH_REDIRECT_URI=https://${SALES_AGENT_DOMAIN}/admin/auth/google/callback
```

### 3. Updated Core Application Files ✅

**`src/admin/app.py`**:
- ✅ SESSION_COOKIE_DOMAIN uses `get_session_cookie_domain()`
- ✅ Admin redirect logic uses `get_tenant_url()` and `is_sales_agent_domain()`

**`src/admin/domain_access.py`**:
- ✅ Super admin checks use `get_super_admin_domain()` instead of hardcoded "scope3.com"
- ✅ Domain/email security checks use configured super admin domain

**`src/landing/landing_page.py`**:
- ✅ Base URL generation uses `get_sales_agent_url()`
- ✅ Subdomain extraction uses `extract_subdomain_from_host()`
- ✅ Domain checks use `is_sales_agent_domain()`
- ✅ Tenant URL generation uses `get_tenant_url()`
- ❌ Removed hardcoded "scope3_url" from template context

**`src/core/main.py`**:
- ✅ Subdomain extraction uses `extract_subdomain_from_host()`
- ✅ Domain checks use `is_sales_agent_domain()`

**`src/a2a_server/adcp_a2a_server.py`**:
- ✅ Agent card URL uses `get_a2a_server_url()`
- ✅ Dynamic server URL uses `get_sales_agent_domain()` and `get_a2a_server_url()`

**`src/admin/blueprints/auth.py`**:
- ✅ Subdomain extraction uses domain config functions
- ✅ OAuth redirect URI uses `get_oauth_redirect_uri()`
- ✅ Super admin check uses `get_super_admin_domain()`
- ⚠️ Still needs updates for GAM OAuth callbacks (lines 477, 544)

## What Still Needs to Be Done

### 4. Remaining Admin Blueprints (High Priority)

Files that need updating:
- `src/admin/blueprints/core.py` - Domain routing logic
- `src/admin/blueprints/public.py` - Public routes
- `src/admin/blueprints/schemas.py` - Schema URLs
- `src/admin/blueprints/authorized_properties.py` - Property URLs
- `src/admin/blueprints/auth.py` - GAM OAuth callbacks (lines 477, 544)

### 5. Frontend JavaScript Files (High Priority)

**`static/js/tenant_settings.js`**:
- Lines 889, 1176, 1180, 1232, 1236 - Hardcoded sales-agent.scope3.com URLs

### 6. Configuration Files (Medium Priority)

**`fly.toml`**:
- Line 57: `A2A_SERVER_URL` environment variable

**`config/nginx/nginx.conf`** and **`fly/nginx.conf`**:
- Multiple hardcoded domain references
- Server name configurations
- Proxy header settings

### 7. Core Services (Medium Priority)

**`src/core/schema_validation.py`**:
- Lines 62, 132, 153 - Schema base URLs

**`src/core/config_loader.py`**:
- Line 138 - Comment with example domain

**`src/services/ai_product_service.py`**:
- Line 471 - Documentation URL reference

### 8. Documentation Files (Low Priority)

**`CLAUDE.md`**:
- Line 1210 - Example production URL

**`docs/security.md`**:
- Multiple references to sales-agent.scope3.com in examples

**`docs/webhooks.md`**:
- Line 600 - Documentation URL

**`docs/gcp-service-account-provisioning-setup.md`**:
- Line 131 - Admin UI URL

**`docs/testing/postmortems/*.md`**:
- Multiple test case examples with hardcoded domains

### 9. Test Files (Low Priority - Can use test domains)

**Integration/E2E Tests**:
- `tests/e2e/test_a2a_regression_prevention.py`
- `tests/integration/test_*` - Multiple test files
- `tests/unit/test_*` - Multiple test files

For tests, we can either:
- Use generic test domains (test.example.com)
- Use domain config with TEST environment variables
- Keep hardcoded test domains since they're not used in production

### 10. Templates (Low Priority)

**HTML Templates**:
- `templates/tenant_settings.html`
- `templates/signup_complete.html`
- `templates/signup_onboarding.html`
- `templates/products.html`
- `templates/index.html`
- `templates/login.html`
- `templates/authorized_properties_list.html`
- `src/landing/templates/tenant_landing.html`

Most templates use backend-generated URLs, but some may have hardcoded references.

## Next Steps

### Immediate Actions (Complete Core Functionality):

1. **Update remaining auth.py GAM callbacks**:
   ```python
   # Lines 477 and 544 in src/admin/blueprints/auth.py
   callback_uri = f"{get_sales_agent_url()}/admin/auth/gam/callback"
   ```

2. **Update core.py blueprint** - Similar patterns to auth.py

3. **Update tenant_settings.js** - Replace hardcoded URLs with template variables or API calls

4. **Update fly.toml** - Use environment variable interpolation:
   ```toml
   A2A_SERVER_URL = "${SALES_AGENT_DOMAIN}/a2a"
   ```

### Testing Approach:

1. **Set environment variables** in `.env.secrets`:
   ```bash
   BASE_DOMAIN=example.com
   SALES_AGENT_DOMAIN=sales-agent.example.com
   ADMIN_DOMAIN=admin.sales-agent.example.com
   SUPER_ADMIN_DOMAIN=example.com
   ```

2. **Run unit tests**: `./run_all_tests.sh quick`

3. **Check for import errors**: Verify domain_config imports work

4. **Manual testing**: Start services and verify domain generation

### Documentation Updates:

1. Update CLAUDE.md with new domain configuration instructions
2. Update all docs/ examples to use ${SALES_AGENT_DOMAIN} placeholders
3. Add migration guide for existing deployments

## Impact Assessment

### Breaking Changes:
- **Environment Variables Required**: New deployments must set domain configuration
- **OAuth Redirect URIs**: Must update Google OAuth settings with new domain
- **Session Cookies**: Domain change requires re-authentication
- **Existing Deployments**: Need migration plan for Scope3-specific deployments

### Backwards Compatibility:
- Domain config functions provide defaults (example.com)
- No breaking changes to database schema
- No breaking changes to AdCP protocol compliance
- Tests need updating but logic unchanged

## Benefits

1. **Vendor Neutral**: No Scope3 branding in codebase
2. **Configurable**: Easy to deploy with any domain
3. **Maintainable**: Centralized domain logic
4. **Testable**: Can use test domains in CI/CD
5. **Documented**: Clear environment variable requirements

## Files Modified So Far

- ✅ `.env.example`
- ✅ `src/core/domain_config.py` (new file)
- ✅ `src/admin/app.py`
- ✅ `src/admin/domain_access.py`
- ✅ `src/landing/landing_page.py`
- ✅ `src/core/main.py`
- ✅ `src/a2a_server/adcp_a2a_server.py`
- ✅ `src/admin/blueprints/auth.py` (partial)

## Estimated Remaining Work

- **High Priority**: 2-3 hours (core blueprints + JavaScript)
- **Medium Priority**: 1-2 hours (config files + services)
- **Low Priority**: 2-3 hours (docs + tests)
- **Testing**: 1-2 hours (comprehensive testing)

**Total**: 6-10 hours of focused development work
