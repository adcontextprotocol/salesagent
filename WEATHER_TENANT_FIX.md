# Weather Tenant Access - Quick Fix Guide

## Problem
Weather team (including Jay Lee at yoon.lee@weather.com) cannot access the Weather tenant.

## Cause
Tenant exists but is missing access control configuration (no `authorized_domains` or `authorized_emails` set).

## Solution - Run on Production Server

### Option 1: Automated Fix Script (RECOMMENDED)
```bash
uv run python scripts/fix_weather_tenant_access.py --fix-all
```

This will:
- ✅ Add `weather.com` domain (grants access to all @weather.com users)
- ✅ Add Jay Lee's email specifically
- ✅ Create Jay Lee as an admin user

### Option 2: Quick Python Commands
```bash
uv run python -c "
from src.admin.domain_access import add_authorized_domain, add_authorized_email, ensure_user_in_tenant

# Add domain
add_authorized_domain('weather', 'weather.com')

# Add Jay Lee
add_authorized_email('weather', 'yoon.lee@weather.com')
ensure_user_in_tenant('yoon.lee@weather.com', 'weather', 'admin', 'Jay Lee')
"
```

### Option 3: Database Direct (if Python not available)
```sql
UPDATE tenants
SET authorized_domains = '["weather.com"]',
    authorized_emails = '["yoon.lee@weather.com"]'
WHERE name ILIKE '%weather%';
```

## Verification
```bash
uv run python scripts/fix_weather_tenant_access.py --check
```

Expected:
```
✅ Found Weather tenant: weather
   Authorized Domains: ['weather.com']
   Authorized Emails: ['yoon.lee@weather.com']
   Users: 1
```

## After Fix
1. Jay Lee can log in at the admin URL
2. All @weather.com users can access the tenant
3. Jay can add more admins through the UI: `Settings > Account > Access Control`

## Files Created
- `/scripts/fix_weather_tenant_access.py` - Automated fix script
- `/docs/WEATHER_TENANT_ACCESS_ISSUE.md` - Detailed documentation

## Technical Details
- Access control uses `authorized_domains` (whole domain) and `authorized_emails` (individual users)
- Super admins (@scope3.com) can always access all tenants
- Code: `src/admin/domain_access.py`
