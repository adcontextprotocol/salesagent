# Preventing Tenant Lockout - Design Flaw Analysis

## The Problem

Weather tenant was created **without access control** configured, resulting in:
- No `authorized_domains`
- No `authorized_emails`
- Result: **Nobody could access the tenant** (except Scope3 super admins)

## Root Cause: Missing Validation

### Current Behavior
When creating a tenant via API or UI:

```python
# tenant_management_api.py:150-168
email_list = data.get("authorized_emails", [])  # Defaults to []
authorized_domains = data.get("authorized_domains", [])  # Defaults to []

# NO VALIDATION that at least one is set!
new_tenant = Tenant(
    authorized_emails=json.dumps(email_list),
    authorized_domains=json.dumps(authorized_domains)
)
```

### UI Form (`templates/create_tenant.html`)
```html
<!-- Lines 40-52: Neither field is required! -->
<input type="text" name="authorized_emails" placeholder="...">
<input type="text" name="authorized_domains" placeholder="...">
```

**Result**: User can create tenant without setting either field → **instant lockout**

## Recommended Fixes

### Fix 1: API Validation (Recommended)
Add validation to reject tenants with no access control:

```python
# In create_tenant() after line 154:
email_list = data.get("authorized_emails", [])
creator_email = data.get("creator_email")
if creator_email and creator_email not in email_list:
    email_list.append(creator_email)

domain_list = data.get("authorized_domains", [])

# NEW VALIDATION
if not email_list and not domain_list:
    return jsonify({
        "error": "Must specify at least one authorized email or domain for tenant access"
    }), 400
```

**Pros**:
- Catches the issue at API level (works for UI and API clients)
- Fail-fast with clear error message
- Forces explicit decision about access control

**Cons**:
- Breaking change for any automation that creates tenants

### Fix 2: Auto-Add Creator Email (Fallback)
If no access control specified, automatically add creator's email:

```python
# After line 154:
email_list = data.get("authorized_emails", [])
creator_email = data.get("creator_email")
domain_list = data.get("authorized_domains", [])

# NEW: Auto-add creator if no access control specified
if not email_list and not domain_list and creator_email:
    email_list.append(creator_email)
    logger.warning(f"No access control specified for tenant {data['name']}, auto-adding creator {creator_email}")

# Still fail if we have nothing
if not email_list and not domain_list:
    return jsonify({
        "error": "Must specify at least one authorized email or domain, or provide creator_email"
    }), 400
```

**Pros**:
- Graceful fallback prevents lockout
- Still requires creator_email or explicit access control

**Cons**:
- Hides the issue rather than forcing explicit configuration
- Creator might forget to add their team

### Fix 3: UI Validation (Client-Side)
Make at least one field required in the UI:

```html
<!-- In create_tenant.html -->
<script>
function validateAccessControl() {
    const emails = document.getElementById('authorized_emails').value.trim();
    const domains = document.getElementById('authorized_domains').value.trim();

    if (!emails && !domains) {
        alert('Please specify at least one authorized email or domain');
        return false;
    }
    return true;
}
</script>

<form method="POST" onsubmit="return validateAccessControl()">
```

**Pros**:
- Immediate feedback to user
- No server roundtrip for validation

**Cons**:
- Only helps UI users (API clients still vulnerable)
- Can be bypassed

## Recommendation: Implement All Three

1. **API validation** (Fix 1) - Primary defense
2. **Auto-add creator** (Fix 2) - Graceful fallback
3. **UI validation** (Fix 3) - Better UX

Combined approach:
```python
# Pseudo-code for combined fix
if not authorized_emails and not authorized_domains:
    if creator_email:
        # Fallback: auto-add creator with warning
        authorized_emails = [creator_email]
        log_warning(f"Auto-adding creator {creator_email} as only authorized user")
    else:
        # Fail: no way to grant access
        return error("Must specify access control or creator_email")
```

## Additional Improvements

### 1. Add Health Check
Prevent tenants from going live with no access:

```python
def validate_tenant_access_control(tenant_id):
    """Check if tenant has valid access control."""
    tenant = get_tenant(tenant_id)

    if not tenant.authorized_emails and not tenant.authorized_domains:
        return False, "No access control configured"

    return True, "OK"
```

### 2. Admin UI Warning
Show warning in admin UI when tenant has no access control:

```html
{% if not tenant.authorized_emails and not tenant.authorized_domains %}
<div class="alert alert-warning">
    ⚠️ Warning: This tenant has no access control configured.
    Nobody can access it except super admins.
    <a href="/tenant/{{ tenant.id }}/settings/access">Configure Access</a>
</div>
{% endif %}
```

### 3. Audit Log Entry
Log when tenants are created without access control:

```python
if not email_list and not domain_list:
    audit_log(
        tenant_id=tenant_id,
        action="tenant_created_without_access_control",
        severity="warning",
        details="Tenant created with no authorized users"
    )
```

## Migration Path

For existing tenants with no access control:

```sql
-- Find locked-out tenants
SELECT tenant_id, name, subdomain
FROM tenants
WHERE (authorized_emails IS NULL OR authorized_emails = '[]')
  AND (authorized_domains IS NULL OR authorized_domains = '[]');
```

Run the fix script we created:
```bash
uv run python scripts/fix_weather_tenant_access.py --check
```

## Related Files

- API: `src/admin/tenant_management_api.py:114-277` (create_tenant)
- UI: `templates/create_tenant.html:40-52` (access control fields)
- Fix script: `scripts/fix_weather_tenant_access.py`
- Access control: `src/admin/domain_access.py`

## Testing

Add test cases for:
1. ❌ Creating tenant with no access control → should fail
2. ✅ Creating tenant with email only → should succeed
3. ✅ Creating tenant with domain only → should succeed
4. ✅ Creating tenant with creator_email but no explicit access → should auto-add creator
5. ❌ Creating tenant with no access AND no creator → should fail

## Conclusion

This was a **preventable issue** caused by:
1. Missing validation at the API level
2. Optional UI fields without client-side checks
3. No defaults or fallbacks

The Weather tenant fix is a **symptom fix**. We need the **root cause fix** (validation) to prevent this from happening again.
