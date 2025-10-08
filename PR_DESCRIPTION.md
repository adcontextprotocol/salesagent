# Consolidate Adapter Configuration: Naming Templates Now Work Across All Adapters

## Summary

Consolidates order and line item naming templates from GAM-specific configuration to tenant-level business rules, making them available across all adapters (GAM, Mock, Kevel). Also reorganizes Admin UI settings into clearer conceptual buckets.

## Motivation

**Problem**: Naming templates were GAM-specific, scattered across settings, and duplicated in adapter code. Users had to reconfigure templates when switching adapters.

**Solution**: Move naming templates to tenant level as a "business rule" - a policy about how the organization operates, independent of infrastructure choices.

## Changes

### 1. Shared Naming Utilities (`src/core/utils/naming.py`)
- Extracted naming template logic from GAM-specific location
- Adapter-agnostic implementation works across all adapters
- Supports fallback syntax: `{campaign_name|promoted_offering}`
- 15 comprehensive unit tests (all passing ✅)

### 2. Mock Adapter Support
- Mock adapter now uses naming templates just like GAM
- Generates properly formatted order/line item names
- Reads from `tenant.order_name_template` and `tenant.line_item_name_template`

### 3. Database Schema
- Added columns to `tenants` table:
  - `order_name_template` VARCHAR(500)
  - `line_item_name_template` VARCHAR(500)
- Alembic migration migrates existing GAM templates to tenant records
- Backward compatible (keeps old columns for 1-2 releases)

### 4. Admin UI Reorganization
**Navigation: 11 sections → 8 sections (27% reduction)**

**Before:**
- ⚙️ General (mixed identity + business rules)
- 🖥️ Ad Server (mixed infrastructure + business rules)
- 📊 Inventory
- 📦 Products
- 🎨 Creative Formats
- 👥 Advertisers
- 🔗 Integrations
- 🔑 API & Tokens
- 👤 Users & Access
- 🔧 Advanced
- ⚠️ Danger Zone

**After:**
- 🏢 **Account** (identity & access control)
- 🖥️ **Ad Server** (infrastructure only)
- 📋 **Business Rules** ⭐ NEW (budget, naming, approvals, features)
- 📊 Inventory
- 📦 Products
- 👥 Advertisers
- 🔗 Integrations
- ⚠️ Danger Zone

**Business Rules Section** consolidates:
- Budget controls (max daily budget)
- Naming conventions (order/line item templates)
  - Live preview with sample data
  - Quick-start presets (Simple, Campaign-First, Detailed)
  - Variable reference and validation
  - Adapter support indicators
- Approval workflow (manual approval, human review)
- Features (AXE signals)

### 5. Backend API
- New endpoint: `POST /tenant/{tenant_id}/settings/business-rules`
- Updates all business rules in single transaction
- JSON response with success notifications

### 6. JavaScript Updates
- `saveBusinessRules()` - Saves via AJAX with floating success notification
- `updateNamingPreview()` - Works with both GAM and Business Rules sections
- `useNamingPreset()` - Dual-section support
- Live preview updates as templates change

## Testing

### Unit Tests
```bash
uv run pytest tests/unit/test_naming_utils.py -v
# 15 tests covering all naming functionality - all passing ✅
```

### Integration Tests
```bash
uv run pytest tests/integration/test_gam_lifecycle.py -v
# GAM adapter tests pass with new imports ✅
```

### Manual Testing Checklist
- [ ] Navigate to http://localhost:8003/tenant/{id}/settings
- [ ] Click "Business Rules" section
- [ ] Verify fields populated from database
- [ ] Test quick-start presets
- [ ] Edit templates and verify live preview updates
- [ ] Save changes and verify success notification
- [ ] Refresh page and verify persistence
- [ ] Create media buy with GAM adapter - verify order name uses template
- [ ] Create media buy with Mock adapter - verify order name uses template

## Migration

**Required before deployment:**
```bash
uv run alembic upgrade head
```

**Migration does:**
1. Adds `order_name_template` and `line_item_name_template` to `tenants` table
2. Copies existing values from `adapter_config` (GAM) to `tenants`
3. Sets sensible defaults for new tenants
4. Keeps old columns for backward compatibility

**Rollback:**
```bash
uv run alembic downgrade -1
```

## Files Changed

**Created (4):**
- `src/core/utils/naming.py` - Shared naming utilities
- `src/core/utils/__init__.py` - Module exports
- `tests/unit/test_naming_utils.py` - 15 comprehensive tests
- `alembic/versions/ebcb8dda247a_add_naming_templates_to_tenants.py` - Migration

**Modified (6):**
- `src/adapters/google_ad_manager.py` - Updated imports
- `src/adapters/gam/managers/workflow.py` - Updated imports
- `src/adapters/mock_ad_server.py` - Added naming template support (~40 lines)
- `src/core/database/models.py` - Added 2 columns to Tenant model
- `templates/tenant_settings.html` - Major reorganization (~150 lines added)
- `src/admin/blueprints/settings.py` - Added business rules endpoint (~80 lines)
- `CLAUDE.md` - Updated documentation with new settings structure

## Benefits

✅ **DRY**: Single source of truth for naming logic
✅ **Adapter-agnostic**: Works across GAM, Mock, and future adapters
✅ **Better UX**: Clear organization (Account → Infrastructure → Business Rules)
✅ **Discoverable**: Naming templates easy to find regardless of adapter
✅ **Live preview**: See exactly what names will look like
✅ **Backward compatible**: Graceful migration path

## Breaking Changes

None. Migration preserves existing data and old columns remain for backward compatibility.

## Future Work

- Remove old naming template UI from GAM section (now redundant)
- Consolidate remaining scattered sections (Users & Access, API & Tokens)
- Remove old `adapter_config` columns after 1-2 releases
- Add naming template support to Kevel adapter

## Related

- Addresses long-standing issue with GAM-specific templates
- Enables mock adapter to properly test naming behavior
- Sets pattern for future business rule consolidation
