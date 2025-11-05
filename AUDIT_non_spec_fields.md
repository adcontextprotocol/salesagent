# Audit: Non-AdCP Spec Fields in Creative Model

## Executive Summary

The `Creative` class contains **20+ fields that are NOT in the official AdCP v1 spec**. This audit identifies their usage across the codebase to assess the impact of removing them for strict spec compliance.

## Official AdCP v1 Spec

**Source:** https://adcontextprotocol.org/schemas/v1/core/creative-asset.json

**ONLY these fields are allowed:**
- Required: `creative_id`, `name`, `format_id`, `assets`
- Optional: `inputs`, `tags`, `approved`

## Non-Spec Fields in Current Creative Model

### 1. Legacy Content Fields (Should be in assets dict)

#### `url` / `content_uri`
- **Lines:** schemas.py:1326-1330
- **Usage in source:**
  - schemas.py:1561 - get_creative_type()
  - schemas.py:1592 - get_primary_content_url()
  - schemas.py:1613 - validate()
  - helpers/creative_helpers.py:143, 147, 148 - asset conversion
- **Usage in tests:**
  - 5 files reference this
- **Impact:** MEDIUM - Used for backward compat, can extract from assets
- **Migration:** Extract URL from assets dict instead

#### `media_url`
- **Lines:** schemas.py:1354
- **Usage in source:**
  - schemas.py:1561, 1592, 1613 - creative type detection
  - tools/creatives.py:1779 - sync_creatives
  - adapters/xandr.py:826 - Xandr adapter
  - helpers/creative_helpers.py:152 - asset conversion
- **Usage in tests:**
  - 5 test files
- **Impact:** MEDIUM - Used by Xandr adapter and conversion
- **Migration:** Extract from assets dict

#### `click_url` / `click_through_url`
- **Lines:** schemas.py:1355
- **Usage in source:**
  - helpers/creative_helpers.py:156 - asset conversion
- **Usage in tests:**
  - Multiple references
- **Impact:** LOW - Should be URL asset in assets dict
- **Migration:** Use assets.click_url with url_type="clickthrough"

#### `width`, `height`, `duration`
- **Lines:** schemas.py:1358-1360
- **Usage in source:**
  - helpers/creative_helpers.py:160-165 - asset conversion
- **Usage in tests:**
  - integration_v2/test_creative_lifecycle_mcp.py:222-235 - checks width/height in database
- **Impact:** LOW - Should be in asset objects
- **Migration:** Extract from assets.{asset_id}.width/height

### 2. Third-Party/Native Creative Fields

#### `snippet`, `snippet_type`
- **Lines:** schemas.py:1387-1392
- **Usage in source:**
  - schemas.py:1554-1624 - get_creative_type(), validation
  - tools/creatives.py:1795 - sync_creatives
  - helpers/creative_helpers.py:133, 148 - asset conversion
- **Usage in tests:**
  - helpers/gam_mock_factory.py:145
  - integration/test_gam_validation_integration.py:271
  - integration/test_impression_tracker_flow.py:57
- **Impact:** MEDIUM - Used for third-party tag creatives
- **Migration:** Could use HTML asset in assets dict with asset_type="html"

#### `template_variables`
- **Lines:** schemas.py:1395-1410
- **Usage in source:**
  - helpers/creative_helpers.py:140 - native creative conversion
- **Usage in tests:**
  - integration/test_gam_validation_integration.py:274
  - integration/test_impression_tracker_flow.py:86
- **Impact:** LOW - Used for native ads
- **Migration:** Could use text assets in assets dict

### 3. Workflow/Internal Fields

#### `status`
- **Lines:** schemas.py:1363
- **Usage in source:**
  - Widely used throughout for approval workflow
- **Usage in tests:**
  - Many references
- **Impact:** CRITICAL - Core workflow field
- **Migration:** KEEP (internal field, not in protocol)

#### `platform_id`
- **Lines:** schemas.py:1364
- **Usage in source:**
  - Used to track ad server IDs
- **Impact:** MEDIUM - Used by adapters
- **Migration:** KEEP (internal field)

#### `review_feedback`
- **Lines:** schemas.py:1365
- **Impact:** LOW - Review comments
- **Migration:** KEEP (internal field)

#### `compliance`
- **Lines:** schemas.py:1368
- **Impact:** LOW - Compliance status
- **Migration:** KEEP (internal field)

#### `package_assignments`
- **Lines:** schemas.py:1371-1373
- **Impact:** MEDIUM - Links creatives to packages
- **Migration:** KEEP (internal field)

#### `delivery_settings`
- **Lines:** schemas.py:1413-1424
- **Impact:** LOW - Platform-specific config
- **Migration:** KEEP or move to database only

### 4. Internal Processing Fields

#### `principal_id`, `group_id`, `created_at`, `updated_at`
- **Lines:** schemas.py:1428-1431
- **Impact:** CRITICAL - Required for multi-tenancy and audit
- **Migration:** KEEP (internal fields, recently made optional)

#### `has_macros`, `macro_validation`, `asset_mapping`, `metadata`
- **Lines:** schemas.py:1432-1435
- **Impact:** MEDIUM - Used for macro processing
- **Migration:** KEEP (internal fields)

## Source Code Impact Analysis

### Files Using Non-Spec Fields

1. **src/core/schemas.py**
   - get_creative_type() - uses media_url, snippet, url
   - get_snippet_content() - uses snippet, url
   - get_primary_content_url() - uses media_url, url
   - validate() - checks snippet, media_url fields

2. **src/core/helpers/creative_helpers.py**
   - _convert_creative_to_adapter_asset() - uses media_url, url, click_url, width, height, duration, snippet, template_variables

3. **src/core/tools/creatives.py**
   - _sync_creatives_impl() - accepts media_url, snippet

4. **src/adapters/xandr.py**
   - Uses media_url for asset conversion

### Test Files Using Non-Spec Fields

- tests/unit/test_adcp_contract.py
- tests/unit/test_sync_creatives_assignment_reporting.py
- tests/integration/test_gam_validation_integration.py
- tests/integration/test_impression_tracker_flow.py
- tests/integration/test_mock_ai_per_creative.py
- tests/integration_v2/test_creative_lifecycle_mcp.py
- tests/unit/helpers/gam_mock_factory.py

## Recommendations

### Option 1: Strict Compliance (Remove All Non-Spec Fields)

**Remove entirely:**
- ❌ url/content_uri (extract from assets)
- ❌ media_url (extract from assets)
- ❌ click_url (use URL asset in assets dict)
- ❌ width, height, duration (in asset objects)
- ❌ snippet, snippet_type (use HTML asset)
- ❌ template_variables (use text assets)
- ❌ delivery_settings (move to database or remove)
- ❌ package_assignments (move to database relationship)
- ❌ platform_id (move to database only)
- ❌ review_feedback (move to database only)
- ❌ compliance (move to database only)

**Keep (internal, not in protocol):**
- ✅ principal_id, created_at, updated_at (multi-tenancy/audit)
- ✅ status (workflow)
- ✅ has_macros, macro_validation, asset_mapping, metadata (processing)

**Breaking changes:**
- All adapters need updates (GAM, Xandr, Mock)
- creative_helpers.py conversion functions need rewrite
- ~10 test files need updates
- Database serialization needs review

**Estimated effort:** 2-3 days

### Option 2: Hybrid Approach (Current State)

**Keep as-is:**
- Accept both AdCP-compliant input AND legacy fields
- Internal fields optional for input
- Filter non-spec fields in responses

**Pros:**
- Backward compatible
- Gradual migration path
- Works with existing code

**Cons:**
- Confusing for clients (which format to use?)
- Violates spec purity
- Maintenance burden

### Option 3: Deprecation Path

**Phase 1 (Now):**
- Accept both formats
- Add warnings for non-spec fields
- Update docs to show correct format

**Phase 2 (Next release):**
- Mark non-spec fields as deprecated
- Require assets dict to be populated
- Emit deprecation warnings

**Phase 3 (Future release):**
- Remove non-spec fields
- Strict AdCP compliance only

## Recommendation

Given the Slack conversation showing clients using non-spec format, I recommend **Option 3: Deprecation Path**.

**Immediate actions:**
1. Add validation that requires `assets` dict to be populated (not empty)
2. Add deprecation warnings when non-spec fields are used
3. Update documentation to show correct format
4. Provide migration guide

**This allows:**
- Fixing issue #703 (current PR)
- Not breaking existing clients
- Clear migration path to strict compliance
