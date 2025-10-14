# Weather Tenant Access Issue - Resolution Guide

## Issue Summary

Weather team (including Jay Lee at yoon.lee@weather.com) cannot access the Weather tenant, even though it was previously created.

## Root Cause

The Weather tenant exists in production but is **missing access control configuration**. The system uses two authorization mechanisms:

1. **Domain-based access** (`authorized_domains`): Grants access to all users with a specific email domain (e.g., `@weather.com`)
2. **Email-based access** (`authorized_emails`): Grants access to specific individual email addresses

When a tenant is created without proper access control configuration, even the intended users cannot access it.

## Solution

### For Production (Immediate Fix Required)

A Scope3 super admin needs to run one of the following on the **production server**:

#### Option 1: Quick Fix Script (Recommended)

```bash
# SSH to production server
ssh production-server

# Run the fix script
uv run python scripts/fix_weather_tenant_access.py --fix-all
```

This will:
- Add `weather.com` to authorized domains (gives access to all @weather.com users)
- Add Jay Lee's email to authorized emails
- Create Jay Lee as an admin user

#### Option 2: Manual Python Commands

```python
from src.admin.domain_access import add_authorized_domain, add_authorized_email, ensure_user_in_tenant

# Add domain (recommended - gives access to all @weather.com users)
add_authorized_domain(tenant_id="weather", domain="weather.com")

# Add Jay Lee as specific authorized user
add_authorized_email(tenant_id="weather", email="yoon.lee@weather.com")

# Create user record for Jay Lee
ensure_user_in_tenant(
    email="yoon.lee@weather.com",
    tenant_id="weather",
    role="admin",
    name="Jay Lee"
)
```

#### Option 3: Direct Database Update (Last Resort)

```sql
-- Check current tenant configuration
SELECT tenant_id, name, authorized_domains, authorized_emails
FROM tenants
WHERE name ILIKE '%weather%';

-- Add weather.com to authorized_domains
UPDATE tenants
SET authorized_domains = '["weather.com"]'
WHERE name ILIKE '%weather%';

-- Add Jay's email to authorized_emails
UPDATE tenants
SET authorized_emails = '["yoon.lee@weather.com"]'
WHERE name ILIKE '%weather%';
```

### Verification

After applying the fix, verify access:

```bash
# Check tenant configuration
uv run python scripts/fix_weather_tenant_access.py --check
```

Expected output:
```
✅ Found Weather tenant: weather
   Name: Weather
   Subdomain: weather
   Active: True
   Authorized Domains: ['weather.com']
   Authorized Emails: ['yoon.lee@weather.com']
   Users: 1
     - yoon.lee@weather.com (admin, active=True)
```

## How Access Control Works

### Domain-Based Access
When a user with email `user@weather.com` logs in:
1. System extracts domain: `weather.com`
2. Looks for tenants with `weather.com` in `authorized_domains`
3. Grants access if found

**Pros**:
- All employees automatically get access
- No need to add individual emails

**Cons**:
- Anyone with that email domain gets access

### Email-Based Access
When a user logs in with a specific email:
1. System checks all tenants' `authorized_emails` lists
2. Grants access to any tenant that explicitly lists the email

**Pros**:
- Fine-grained control
- Works for external contractors/partners

**Cons**:
- Must add each user individually

### Super Admin Access
Users with `@scope3.com` emails are super admins and can:
- Access all tenants
- Modify access control settings
- Create new tenants

## Prevention

To prevent this issue in the future:

1. **When creating tenants**, always configure access control:
   - Add the organization's domain to `authorized_domains`, OR
   - Add at least one admin email to `authorized_emails`

2. **Use the tenant creation script** that includes access setup:
   ```bash
   uv run python scripts/setup/create_tenant.py \
     --name "Organization Name" \
     --subdomain "org" \
     --domain "org.com" \
     --admin-email "admin@org.com"
   ```

3. **Document the admin contact** during tenant creation

## Admin UI Settings

Once Jay Lee has access, additional users can be managed through the Admin UI:

1. Navigate to: `Settings > Account > Access Control`
2. Add domains or individual emails
3. Assign roles: `admin`, `manager`, `viewer`

## Technical Details

### Database Schema

```sql
tenants (
  tenant_id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(200),
  authorized_domains JSONB,  -- Array of domains
  authorized_emails JSONB,   -- Array of emails
  ...
)

users (
  user_id VARCHAR(50) PRIMARY KEY,
  tenant_id VARCHAR(50),
  email VARCHAR(255),
  role VARCHAR(50),  -- admin, manager, viewer
  is_active BOOLEAN,
  ...
)
```

### Code References

- Access control logic: `src/admin/domain_access.py`
- Auth middleware: `src/admin/auth.py`
- Tenant model: `src/core/database/models.py:38-100`

## Support Contacts

For issues with this fix:
- Check logs: `fly logs --app adcp-sales-agent` (or your deployment logs)
- Scope3 engineering team
- Reference: This document and `scripts/fix_weather_tenant_access.py`
