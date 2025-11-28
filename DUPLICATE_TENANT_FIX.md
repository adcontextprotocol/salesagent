# Fix: Prevent Duplicate Tenant Creation for Existing Domains

## Problem Statement

Users with email addresses from domains already associated with existing tenants were able to create additional tenants, resulting in:

1. **Domain Collision**: Multiple tenants claiming the same `authorized_domains` (e.g., 3 separate "Weather Company" tenants all with `weather.com`)
2. **Data Fragmentation**: Organization's data spread across multiple tenant instances
3. **User Confusion**: Users seeing multiple identical tenants in tenant selector
4. **Security Concern**: Bypassing intended single-tenant-per-domain architecture

### Real-World Example

The Weather Company had 3 separate tenant instances:
- `weather` (subdomain: weather) - Created Oct 14, 2025
- `e54a078c` (subdomain: e54a078c) - Created Nov 11, 2025
- `633f34b4` (subdomain: 633f34b4) - Created Nov 20, 2025

All three tenants had `["weather.com"]` in their `authorized_domains`, meaning any `@weather.com` user could access all 3 tenants and create even more.

## Root Cause

The authentication flow allowed users to create new tenants even when their email domain was already claimed:

1. **OAuth Callback** (`auth.py`): Always showed tenant selector with "Create New Account" option
2. **Tenant Selector UI** (`choose_tenant.html`): Always displayed "Create New Account" button
3. **Provision Endpoint** (`public.py`): No validation to prevent duplicate domains
4. **Self-Service Design**: Intentionally permissive to allow multi-org access, but lacked domain uniqueness enforcement

## Solution Overview

Implement **domain-based tenant routing** and **duplicate prevention** at three levels:

### 1. OAuth Callback Auto-Routing (auth.py)
- Check if user's email domain matches an existing tenant's `authorized_domains`
- If user has exactly one domain tenant: **auto-route directly to dashboard**
- If user has multiple tenants: show selector but **hide "Create New Account"**
- Set `session["has_domain_tenant"]` flag for UI conditional rendering

### 2. UI Conditional Rendering (choose_tenant.html)
- Hide "Create New Account" button when `session.has_domain_tenant == True`
- Show informative message: "Your email domain is already associated with an existing account"
- Only allow tenant creation for users with unclaimed email domains

### 3. Server-Side Validation (public.py)
- Add validation in `/signup/provision` endpoint
- Check if email domain already exists in any tenant's `authorized_domains`
- Reject request with clear error message if domain is claimed
- Prevents bypassing UI restrictions via direct POST requests

## Implementation Details

### File Changes

#### 1. src/admin/blueprints/auth.py (Lines 281-356)

**Before:**
```python
# Always show tenant selector (includes "Create New Tenant" option)
flash(f"Welcome {user.get('name', email)}!", "success")
return redirect(url_for("auth.select_tenant"))
```

**After:**
```python
# NEW: Check if user has domain-based tenant access
has_domain_tenant = tenant_access["domain_tenant"] is not None
session["has_domain_tenant"] = has_domain_tenant

# If user has exactly one tenant via domain access, auto-route them directly
if has_domain_tenant and len(tenant_dict) == 1:
    domain_tenant = tenant_access["domain_tenant"]
    # ... ensure user record exists ...
    return redirect(url_for("tenants.dashboard", tenant_id=domain_tenant.tenant_id))

# Show tenant selector (with conditional "Create New Tenant" option)
return redirect(url_for("auth.select_tenant"))
```

**Key Changes:**
- Added `session["has_domain_tenant"]` flag
- Auto-route users with single domain tenant (no selector needed)
- Maintains tenant selector for multi-tenant access scenarios

#### 2. templates/choose_tenant.html (Lines 27-55)

**Before:**
```html
<div style="text-align: center; padding-top: 1rem; border-top: 1px solid #ddd;">
    <p style="margin-bottom: 0.75rem; color: #666; font-size: 0.9rem;">Don't see your account?</p>
    <a href="{{ url_for('public.signup_onboarding') }}" class="btn btn-outline-secondary">
        Create New Account
    </a>
</div>
```

**After:**
```html
{% if not session.get('has_domain_tenant') %}
<div style="text-align: center; padding-top: 1rem; border-top: 1px solid #ddd;">
    <p style="margin-bottom: 0.75rem; color: #666; font-size: 0.9rem;">Don't see your account?</p>
    <a href="{{ url_for('public.signup_onboarding') }}" class="btn btn-outline-secondary">
        Create New Account
    </a>
</div>
{% else %}
<div style="text-align: center; padding-top: 1rem; border-top: 1px solid #ddd;">
    <p style="color: #666; font-size: 0.9rem; margin: 0;">
        <em>Your email domain is already associated with an existing account.</em>
    </p>
</div>
{% endif %}
```

**Key Changes:**
- Conditional rendering based on `session.has_domain_tenant`
- Clear messaging when domain is already claimed
- Separate handling for "no tenants" vs "tenants exist" scenarios

#### 3. src/admin/blueprints/public.py (Lines 117-140)

**Before:**
```python
# Validation
if not publisher_name:
    flash("Publisher name is required", "error")
    return redirect(url_for("public.signup_onboarding"))

# Generate random subdomain and tenant ID (prevents subdomain squatting)
import uuid
tenant_id = str(uuid.uuid4())
```

**After:**
```python
# Validation
if not publisher_name:
    flash("Publisher name is required", "error")
    return redirect(url_for("public.signup_onboarding"))

# Get user info from session
user_email = session.get("user")
email_domain = user_email.split("@")[1] if "@" in user_email else ""

# NEW: Prevent duplicate tenant creation if email domain is already claimed
if email_domain:
    from src.admin.domain_access import find_tenant_by_authorized_domain

    existing_tenant = find_tenant_by_authorized_domain(email_domain)
    if existing_tenant:
        logger.warning(
            f"Prevented duplicate tenant creation: {email_domain} already claimed by tenant {existing_tenant.tenant_id}"
        )
        flash(
            f"Your email domain ({email_domain}) is already associated with an existing account: {existing_tenant.name}. "
            "Please contact your organization's administrator for access.",
            "error",
        )
        return redirect(url_for("auth.login"))

# Generate random subdomain and tenant ID
```

**Key Changes:**
- Server-side domain uniqueness validation
- Clear error messaging with existing tenant name
- Prevents bypassing UI restrictions
- Maintains security even if users manipulate client-side code

## Behavior Changes

### Scenario 1: User from Existing Domain (Single Tenant)
**Email:** `user@weather.com`
**Existing Tenant:** "weather" with `authorized_domains=["weather.com"]`

**Old Behavior:**
1. Show tenant selector with "weather" tenant
2. Display "Create New Account" button
3. User could create duplicate tenant

**New Behavior:**
1. ✅ Auto-route directly to "weather" tenant dashboard
2. ✅ No tenant selector shown (faster UX)
3. ✅ No opportunity to create duplicate

### Scenario 2: User from Existing Domain (Multiple Tenants)
**Email:** `user@weather.com`
**Existing Tenants:** 3 tenants all with `authorized_domains=["weather.com"]`

**Old Behavior:**
1. Show tenant selector with 3 tenants
2. Display "Create New Account" button
3. User could create 4th tenant

**New Behavior:**
1. ✅ Show tenant selector with 3 tenants
2. ✅ Hide "Create New Account" button
3. ✅ Show message: "Your email domain is already associated with an existing account"
4. ✅ User must select from existing tenants

### Scenario 3: User from New Domain
**Email:** `user@newcompany.com`
**Existing Tenants:** None with `authorized_domains` containing "newcompany.com"

**Old Behavior:**
1. Show tenant selector (empty)
2. Display "Create New Account" button
3. User creates new tenant

**New Behavior:**
1. ✅ Show tenant selector (empty)
2. ✅ Display "Create New Account" button (no domain conflict)
3. ✅ User creates new tenant (allowed)
4. ✅ No change to existing functionality

### Scenario 4: User with Email-Only Access (No Domain Access)
**Email:** `contractor@gmail.com`
**Tenant Config:** `authorized_emails=["contractor@gmail.com"]` (NOT `gmail.com` in `authorized_domains`)

**Old Behavior:**
1. Show tenant selector with accessible tenant
2. Display "Create New Account" button
3. User could create new tenant

**New Behavior:**
1. ✅ Show tenant selector with accessible tenant
2. ✅ Display "Create New Account" button (gmail.com not claimed)
3. ✅ User can create new tenant (allowed)
4. ✅ `has_domain_tenant=False` - only email-based access

### Scenario 5: Direct POST to /signup/provision (Bypass Attempt)
**Email:** `user@weather.com`
**Action:** User crafts direct POST request to bypass UI restrictions

**Old Behavior:**
1. Request succeeds
2. Creates duplicate tenant

**New Behavior:**
1. ✅ Server-side validation catches domain conflict
2. ✅ Request rejected with error message
3. ✅ User redirected to login
4. ✅ Logs warning for security monitoring

## Testing Scenarios

Test file created: `tests/unit/test_prevent_duplicate_tenants.py`

Key test cases:
1. ✅ OAuth auto-routing for single domain tenant
2. ✅ Tenant selector shown for multiple tenants
3. ✅ "Create New Account" hidden when domain exists
4. ✅ "Create New Account" shown when domain is unclaimed
5. ✅ Server-side validation rejects duplicate domains
6. ✅ Session flag `has_domain_tenant` set correctly

## Security Considerations

### Defense in Depth
1. **UI Layer**: Hide "Create New Account" button (user-friendly)
2. **Client Session**: Track `has_domain_tenant` flag (fast checks)
3. **Server Validation**: Domain uniqueness check (security boundary)

### Session Flag Security
- `has_domain_tenant` stored in Flask session (server-side)
- Users cannot manipulate session variables directly
- Even if session is compromised, server-side validation prevents abuse

### Logging and Monitoring
- Warning logged when duplicate creation is prevented
- Includes email domain and existing tenant ID
- Enables security monitoring and abuse detection

## Migration Strategy

### No Database Migration Required
This is a **pure application logic change** - no database schema changes.

### Existing Duplicate Tenants
This fix **prevents new duplicates** but does not automatically merge existing ones.

**Recommended cleanup for production:**
1. Identify tenants with duplicate `authorized_domains`
2. Contact organization admins to determine canonical tenant
3. Migrate data from duplicate tenants to canonical tenant
4. Deactivate/delete duplicate tenant records

**Example cleanup for Weather Company:**
```sql
-- Find duplicate tenants
SELECT tenant_id, subdomain, name, authorized_domains, created_at
FROM tenants
WHERE authorized_domains @> '["weather.com"]'
ORDER BY created_at;

-- After confirming with customer, keep oldest tenant (weather)
-- Deactivate duplicates
UPDATE tenants SET is_active = false WHERE tenant_id IN ('e54a078c-7a2d-4db1-8939-8b29b19229d7', '633f34b4-0209-4b86-a4c6-09b0c3fd4b98');
```

## Rollback Plan

If issues arise, rollback is straightforward:

1. **Revert auth.py**: Remove auto-routing and `has_domain_tenant` logic
2. **Revert choose_tenant.html**: Remove conditional rendering
3. **Revert public.py**: Remove server-side validation

No database changes to rollback.

## Future Enhancements

### Potential Improvements
1. **Domain Claim Verification**: Require DNS TXT record verification before claiming domain
2. **Admin UI for Duplicates**: Show super admins duplicate tenants and provide merge tool
3. **Email Notifications**: Notify existing tenant admins when user from their domain attempts signup
4. **Self-Service Access Request**: Allow users to request access to existing tenant instead of hard reject
5. **Subdomain Claiming**: Allow tenants to claim custom subdomains (e.g., `weather.salesagent.com`)

## Testing Checklist

Before deploying to production:

- [ ] Test OAuth login with user from existing domain (single tenant)
- [ ] Test OAuth login with user from existing domain (multiple tenants)
- [ ] Test OAuth login with user from new domain
- [ ] Test OAuth login with email-only access user
- [ ] Test direct POST to /signup/provision with existing domain
- [ ] Test tenant selector UI shows/hides "Create New Account" correctly
- [ ] Test auto-routing redirects to correct tenant dashboard
- [ ] Verify session flag `has_domain_tenant` is set correctly
- [ ] Verify logging works for prevented duplicate creation
- [ ] Test with various email formats (uppercase, mixed case)

## Deployment Notes

**Branch:** `prevent-duplicate-tenant-domains`
**Status:** Ready for review, **DO NOT PUSH TO PRODUCTION**

**Files Changed:**
- `src/admin/blueprints/auth.py` (OAuth callback logic)
- `templates/choose_tenant.html` (UI conditional rendering)
- `src/admin/blueprints/public.py` (Server-side validation)
- `tests/unit/test_prevent_duplicate_tenants.py` (Test documentation)
- `DUPLICATE_TENANT_FIX.md` (This document)

**No Breaking Changes:**
- Existing single-tenant users: Better UX (auto-routing)
- Existing multi-tenant users: Slightly restricted (no duplicate creation)
- New domain users: No change in functionality

**Recommended Testing Period:**
- Deploy to staging environment
- Test with various user scenarios
- Monitor logs for prevented duplicates
- Get user feedback on auto-routing experience
- Deploy to production after 1 week of staging validation
