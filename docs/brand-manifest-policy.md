# Brand Manifest Policy Configuration

## Overview

The brand manifest policy controls when a brand_manifest is required in `get_products` and `create_media_buy` requests. This is configured per-tenant in the database.

## Policy Options

### 1. `require_auth` (Default - Recommended)
- **Authentication**: Required
- **Brand Manifest**: Optional
- **Pricing**: Shown to authenticated users
- **Use Case**: Standard B2B model where advertisers must authenticate but don't need to provide brand context for every request
- **Testing**: Best for testing and development environments

### 2. `require_brand` (Strictest)
- **Authentication**: Required
- **Brand Manifest**: Required
- **Pricing**: Shown only when brand manifest provided
- **Use Case**: Publishers offering bespoke/custom products that require brand context
- **Testing**: More restrictive, harder for testing

### 3. `public` (Most Open)
- **Authentication**: Not required
- **Brand Manifest**: Optional
- **Pricing**: Hidden (only generic product info shown)
- **Use Case**: Public product catalog browsing
- **Testing**: Good for anonymous browsing, but pricing not shown

## Configuration

### Via Admin UI

1. Log into the admin UI at `https://admin.your-domain.com`
2. Navigate to **Tenant Settings** → **Policies & Workflows**
3. Find the **Brand Manifest Policy** dropdown
4. Select `require_auth` (recommended for testing)
5. Save changes

### Via Database (Direct SQL)

```sql
-- Update a specific tenant
UPDATE tenants
SET brand_manifest_policy = 'require_auth'
WHERE tenant_id = 'your-tenant-id';

-- Update all tenants
UPDATE tenants
SET brand_manifest_policy = 'require_auth';
```

### Via Python Script

Run the provided script to update all tenants:

```bash
# From project root
uv run python scripts/update_brand_manifest_policy.py
```

This will update all tenants to use `require_auth` policy.

### Via Fly.io (Production)

If deploying on Fly.io, you can run the script in production:

```bash
# SSH into production
fly ssh console --app adcp-sales-agent

# Run the update script
python scripts/update_brand_manifest_policy.py
```

Or update directly via database:

```bash
# Connect to production database
fly postgres connect --app adcp-sales-agent-db

# Run SQL update
UPDATE tenants SET brand_manifest_policy = 'require_auth';
```

## Testing

After updating the policy, test with:

```bash
# Test get_products without brand_manifest (should work with require_auth)
uv run pytest tests/unit/test_brand_manifest_optional.py -v

# Test full integration
uv run pytest tests/integration/ -k "get_products" -v
```

## Migration History

- **PR #663**: Added `brand_manifest_policy` system with three policy options
- **Migration 6f05f4179c33**: Added column with default `require_brand`
- **Migration 378299ad502f**: Changed default to `require_auth` for new tenants

## Implementation Details

The policy is enforced in `src/core/tools/products.py` in the `_get_products_impl()` function:

```python
# Policy enforcement
if policy == "require_brand" and not brand_manifest:
    raise ToolError("Brand manifest required by tenant policy")
elif policy == "require_auth" and not principal_id:
    raise ToolError("Authentication required by tenant policy")
# public policy allows all requests
```

Pricing visibility logic:
- `public`: No pricing shown
- `require_auth`: Pricing shown if authenticated
- `require_brand`: Pricing shown if authenticated AND brand_manifest provided
