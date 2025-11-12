# Route Conflict Analysis and Resolution Plan

## Summary
13 route conflicts exist between blueprints. Analysis shows these fall into 4 categories:

1. **NOT CONFLICTS** (RESTful design - different HTTP methods): 3 cases
2. **LEGITIMATE DUPLICATES** (same blueprint, two endpoints): 1 case
3. **LEGACY DUPLICATES** (tenants.py vs dedicated blueprints): 7 cases
4. **OPERATIONAL DUPLICATES** (operations.py vs dedicated blueprints): 2 cases

## Detailed Analysis

### Category 1: NOT CONFLICTS (Different HTTP Methods - KEEP BOTH)

#### 1. `/api/v1/tenant-management/tenants`
- ✅ **CORRECT** - RESTful design
- `GET` → tenant_management_api.list_tenants
- `POST` → tenant_management_api.create_tenant
- **Action**: Update whitelist checker to ignore different HTTP methods

#### 2. `/api/v1/tenant-management/tenants/<tenant_id>`
- ✅ **CORRECT** - RESTful design
- `GET` → tenant_management_api.get_tenant
- `PUT` → tenant_management_api.update_tenant
- `DELETE` → tenant_management_api.delete_tenant
- **Action**: Update whitelist checker to ignore different HTTP methods

#### 3. `/tenant/<tenant_id>/products/<product_id>/inventory`
- ✅ **CORRECT** - RESTful design
- `GET` → products.get_product_inventory
- `POST` → products.assign_inventory_to_product
- **Action**: Update whitelist checker to ignore different HTTP methods

---

### Category 2: LEGITIMATE DUPLICATE (Same Blueprint - REMOVE ONE)

#### 4. `/tenant/<tenant_id>/update`
- 🔴 **DUPLICATE** in tenants.py blueprint
- Line 387: `@tenants_bp.route("/<tenant_id>/update")` → `update()`
  - Uses: `@log_admin_action("update")`, `@require_tenant_access()`
  - Updates: name, subdomain, billing_plan
- Line 525: `@tenants_bp.route("/<tenant_id>/update")` → `update_tenant()`
  - Uses: `@require_auth()`
  - Updates: max_daily_budget, enable_axe_signals, human_review_required
  - Has role checks (viewer cannot update)
- **Decision**: REMOVE `update_tenant()` (line 525-560)
  - The first `update()` function uses proper decorators
  - The second function's fields should be merged into first or moved to settings.py
  - Role checks can be added to `update()` function

---

### Category 3: LEGACY DUPLICATES (tenants.py vs Dedicated Blueprints - REMOVE FROM tenants.py)

#### 5. `/tenant/<tenant_id>/users`
- tenants.py (line 563) → tenants.list_users (GET)
- users.py (line 20) → users.list_users (GET)
- **Decision**: REMOVE from tenants.py (keep users.py)
- **Reason**: users.py is dedicated blueprint with cleaner implementation

#### 6. `/tenant/<tenant_id>/users/add`
- tenants.py (line 590) → tenants.add_user (POST)
- users.py (line 54) → users.add_user (POST)
- **Decision**: REMOVE from tenants.py (keep users.py)
- **Reason**: users.py is dedicated blueprint

#### 7. `/tenant/<tenant_id>/users/<user_id>/toggle`
- tenants.py (line 637) → tenants.toggle_user (POST)
- users.py (line 107) → users.toggle_user (POST)
- **Decision**: REMOVE from tenants.py (keep users.py)
- **Reason**: users.py is dedicated blueprint

#### 8. `/tenant/<tenant_id>/users/<user_id>/update_role`
- tenants.py (line 663) → tenants.update_user_role (POST)
- users.py (line 132) → users.update_role (POST)
- **Decision**: REMOVE from tenants.py (keep users.py)
- **Reason**: users.py is dedicated blueprint

#### 9. `/tenant/<tenant_id>/principals/create`
- tenants.py (line 689) → tenants.create_principal (GET, POST)
- principals.py (line 112) → principals.create_principal (GET, POST)
- **Decision**: REMOVE from tenants.py (keep principals.py)
- **Reason**: principals.py is dedicated blueprint

#### 10. `/tenant/<tenant_id>/principal/<principal_id>/update_mappings`
- tenants.py (line ~800) → tenants.update_principal_mappings (POST)
- principals.py → principals.update_mappings (POST)
- **Decision**: REMOVE from tenants.py (keep principals.py)
- **Reason**: principals.py is dedicated blueprint

---

### Category 4: OPERATIONAL DUPLICATES (operations.py vs Dedicated Blueprints)

#### 11. `/tenant/<tenant_id>/orders`
- operations.py (line 35) → operations.orders (GET)
- inventory.py (line 328) → inventory.orders_browser (GET)
- **Analysis**: Need to check which is actively used
- **Decision**: REMOVE from operations.py (keep inventory.orders_browser)
- **Reason**: inventory.py has more complete implementation with sync/get endpoints

#### 12. `/tenant/<tenant_id>/workflows`
- operations.py (line 87) → operations.workflows (GET)
- workflows.py (line 22) → workflows.list_workflows (GET)
- **Decision**: REMOVE from operations.py (keep workflows.py)
- **Reason**: workflows.py is dedicated blueprint with additional routes

---

## Implementation Plan

### Step 1: Remove User Routes from tenants.py
Remove lines 563-684 (list_users, add_user, toggle_user, update_user_role)

### Step 2: Remove Principal Routes from tenants.py
Remove lines 689-910 (create_principal, update_principal_mappings, delete_principal)

### Step 3: Remove Duplicate update_tenant from tenants.py
Remove lines 525-560 (update_tenant function)

### Step 4: Remove Operations Duplicates
- Remove operations.orders (line 35-84)
- Remove operations.workflows (line 87-136)

### Step 5: Update Route Conflict Checker
Modify `.pre-commit-hooks/check_route_conflicts.py` to:
- Remove resolved conflicts from KNOWN_CONFLICTS whitelist
- Ignore conflicts where routes have different HTTP methods (RESTful design)

### Step 6: Verify
- Run route conflict checker: `uv run python .pre-commit-hooks/check_route_conflicts.py`
- Run tests to ensure no broken references
- Check admin UI still works

---

## Routes to Remove

### From tenants.py:
1. `update_tenant()` (line 525-560)
2. `list_users()` (line 563-587)
3. `add_user()` (line 590-634)
4. `toggle_user()` (line 637-660)
5. `update_user_role()` (line 663-684)
6. `create_principal()` (line 689-~780)
7. `update_principal_mappings()` (line ~800-~850)
8. `delete_principal()` (line 911-~940)

### From operations.py:
1. `orders()` (line 35-84)
2. `workflows()` (line 87-136)

---

## Expected Outcome

After implementation:
- 0 NEW route conflicts (pre-commit hook passes)
- 3 remaining conflicts (RESTful - different HTTP methods) - will update checker to ignore these
- Cleaner codebase with dedicated blueprints handling their own routes
- No duplicate maintenance burden
