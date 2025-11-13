# Fix: list_tasks Tenant Context Issue

## Problem

When calling the `list_tasks` MCP tool on the Wonderstruck Sales agent (wonderstruck.sales-agent.scope3.com/mcp), users received the error:

```
Error calling tool 'list_tasks': No tenant context set. Tenant must be set via set_current_tenant()
before calling this function. This is a critical security error - falling back to default tenant
would breach tenant isolation.
```

## Root Cause

The `list_tasks`, `get_task`, and `complete_task` tools in `src/core/main.py` were calling `get_current_tenant()` directly without first establishing the tenant context. This violated the multi-tenant security pattern used throughout the codebase.

The issue occurred because these tools were:
1. Calling `get_current_tenant()` which reads from a ContextVar
2. But never calling `get_principal_from_context()` to establish that context first

## How Tenant Context Works

In this multi-tenant system, tenant context is established through HTTP headers:
- `Host` header (for subdomain routing like `wonderstruck.sales-agent.scope3.com`)
- `Apx-Incoming-Host` header (for Approximated.app virtual hosts)
- `x-adcp-tenant` header (for path-based routing)

The proper flow is:
1. Client sends request with `x-adcp-auth` token + host headers
2. Tool calls `get_principal_from_context(context, require_valid_token=True)`
3. That function:
   - Extracts tenant from headers (via `apx-incoming-host`, `host`, or `x-adcp-tenant`)
   - Validates the auth token belongs to that tenant
   - Sets the tenant context via `set_current_tenant(tenant)`
   - Returns `(principal_id, tenant)`
4. Tool can then safely use `tenant["tenant_id"]` for database queries

## Solution

Updated all three task-related tools to follow the correct pattern used by other working tools (like `get_products`):

### Before (WRONG):
```python
# Get tenant info
tenant = get_current_tenant()  # ❌ Fails because context not set yet
principal_id = _get_principal_id_from_context(context)
```

### After (CORRECT):
```python
# Establish tenant context first (CRITICAL for multi-tenancy)
# This resolves tenant from headers (apx-incoming-host, host, x-adcp-tenant)
# and sets it in the ContextVar before any database queries
principal_id, tenant = get_principal_from_context(context, require_valid_token=True)

if not tenant:
    raise ToolError("No tenant context available. Check x-adcp-auth token and host headers.")

# Set tenant context explicitly for this async context
set_current_tenant(tenant)
```

## Files Changed

- `src/core/main.py`:
  - Fixed `list_tasks()` (line 773-782)
  - Fixed `get_task()` (line 869-876)
  - Fixed `complete_task()` (line 941-948)

## Testing

To verify the fix works:

```bash
# 1. Start the MCP server
docker-compose up -d

# 2. Use MCP client with proper headers:
# - x-adcp-auth: <wonderstruck-api-key>
# - Host: wonderstruck.sales-agent.scope3.com (or Apx-Incoming-Host)

# 3. Call list_tasks:
list_tasks(status="pending", object_type="creative")

# Expected: Should return tasks for the Wonderstruck tenant
```

## Why This Matters

This fix is critical for multi-tenant security:
- **Prevents tenant isolation breaches**: Without proper context, queries could leak data across tenants
- **Enables virtual host routing**: Supports custom domains via Approximated.app
- **Follows established patterns**: Aligns with how all other MCP tools handle authentication

## Related Documentation

- Architecture pattern: `CLAUDE.md` - "MCP/A2A Shared Implementation Pattern"
- Tenant detection: `src/core/auth.py` - `get_principal_from_context()`
- Context management: `src/core/config_loader.py` - `set_current_tenant()`
