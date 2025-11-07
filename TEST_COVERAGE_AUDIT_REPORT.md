# Critical Test Coverage Audit Report
**Date**: 2025-11-06
**Analyst**: Node.js Testing Specialist
**Context**: Post-mortem analysis of `sync_creatives` URL overwrite bug

---

## Executive Summary

A critical data corruption bug in `sync_creatives` went undetected by all existing tests. User-provided URLs were silently overwritten with preview URLs, but tests passed because:

1. **Tests used legacy data structures** - No tests used AdCP-compliant `assets.banner_image.url` format
2. **No roundtrip validation** - Tests didn't verify data preservation through sync→store→retrieve→use flow
3. **Over-mocking hid the issue** - Preview generation was mocked, hiding the overwrite logic
4. **Coverage metrics were misleading** - Buggy code (line 617) was executed but behavior wasn't tested

**Impact**: Production bug affecting all clients using AdCP v2.4+ asset structures with creative formats requiring preview generation.

---

## 1. The Bug Pattern Analysis

### What Went Wrong

**Location**: `src/core/tools/creatives.py:617` (update path) and `line 969` (create path)

**The Bug**:
```python
# Lines 380-405: User URL correctly extracted from assets
url = creative.get("url")
if not url and creative.get("assets"):
    # Extract from assets.banner_image.url (AdCP format)
    for priority_key in ["main", "image", "video", "creative", "content"]:
        if priority_key in assets and isinstance(assets[priority_key], dict):
            url = assets[priority_key].get("url")
            if url:
                break
data["url"] = url  # ✅ User's URL stored correctly

# Lines 594-600: preview_creative called with user's data
preview_result = run_async_in_sync_context(
    registry.preview_creative(
        agent_url=format_obj.agent_url,
        format_id=format_id_str,
        creative_manifest=creative_manifest,  # Contains user's URL
    )
)

# Line 617: UNCONDITIONAL OVERWRITE 🐛
if first_render.get("preview_url"):
    data["url"] = first_render["preview_url"]  # ❌ Overwrites user's URL!
    changes.append("url")
```

**Root Cause**:
- Extraction logic correctly gets user's URL from `assets.banner_image.url`
- Preview generation is called (correctly, for validation)
- Preview result **unconditionally overwrites** the user's URL
- No check: "Was there a user-provided URL? Should we preserve it?"

**Why It's Insidious**:
- The code executes correctly (no exceptions)
- Extraction logic works (URL is found)
- Preview generation works (preview URL returned)
- But **semantic behavior is wrong** (user data lost)

---

## 2. Similar Risky Patterns Found

### High-Risk Data Overwrites (Immediate Action Required)

#### A. Creative Update Path (SAME BUG - lines 536, 896)
**Location**: `src/core/tools/creatives.py:536` (generative output), `line 896` (generative create)

```python
# Line 536: Generative format update
if isinstance(output_format, dict) and output_format.get("url"):
    data["url"] = output_format["url"]  # ❌ Same bug, different path!
    changes.append("url")
```

**Risk**: Generative creatives also overwrite user URLs with generated URLs.

**Impact**: Affects generative formats (AI-generated creatives) in addition to static formats.

**Status**: ⚠️ **CRITICAL - Same vulnerability, different code path**

#### B. Creative Patch Mode URL Update (Medium Risk)
**Location**: `src/core/tools/creatives.py:353-355`

```python
if patch:
    # Patch mode: merge with existing data
    data = existing_creative.data or {}
    if creative.get("url") is not None and data.get("url") != creative.get("url"):
        data["url"] = creative.get("url")  # ✅ Conditional check exists
        changes.append("url")
```

**Risk**: Lower - has conditional check (`if creative.get("url") is not None`).

**Issue**: Doesn't extract from assets structure in patch mode, only checks top-level URL.

**Status**: ⚠️ **MEDIUM - Missing asset extraction in patch mode**

### Medium-Risk Patterns (Review Recommended)

#### C. Preview Response Storage (Potential Metadata Loss)
**Location**: `src/core/tools/creatives.py:603-607`

```python
if preview_result and preview_result.get("previews"):
    # Store full preview response for UI (per AdCP PR #119)
    data["preview_response"] = preview_result  # ✅ Full response stored

    # BUT: Still overwrites URL unconditionally (line 617)
```

**Risk**: Preview response is stored (good!), but URL still overwritten (bad!).

**Status**: ⚠️ **MEDIUM - Incomplete fix, URL overwrite remains**

#### D. Dimension Extraction from Preview (Safe but Related)
**Location**: `src/core/tools/creatives.py:624-633`

```python
dimensions = first_render.get("dimensions", {})
if dimensions.get("width"):
    data["width"] = dimensions["width"]
    changes.append("width")
if dimensions.get("height"):
    data["height"] = dimensions["height"]
    changes.append("height")
```

**Risk**: Low - dimensions should come from preview (they're metadata).

**Status**: ✅ **OK - Expected behavior for dimensions**

### Low-Risk Patterns (Acceptable)

#### E. Click URL Extraction (Safe)
**Location**: `src/core/tools/creatives.py:356-360`

```python
if creative.get("click_url") is not None and data.get("click_url") != creative.get("click_url"):
    data["click_url"] = creative.get("click_url")
    changes.append("click_url")
```

**Status**: ✅ **OK - Conditional check exists, preserves user data**

---

## 3. Test Coverage Gaps (Critical Findings)

### What Tests Are Missing

#### A. **NO TESTS for AdCP-Compliant Asset Structures**

**Current State**:
```bash
$ grep -r "assets.*banner_image\|video_asset" tests/
# Only 2 matches:
tests/unit/test_sync_creatives_async_fix.py:139: "assets": {"banner_image": {"url": "..."}}
tests/unit/test_sync_creatives_async_fix.py:214: "assets": {"banner_image": {"url": "..."}}
```

**Gap**: Only 1 test file uses AdCP format specs. All other tests use:
- Top-level `url` field (legacy structure)
- Generic asset IDs like "main" or "image" (convention, not spec)
- Hardcoded structures (not from cached format specs)

**Impact**: **CRITICAL** - Bug only affects AdCP-compliant structures, which aren't tested.

#### B. **NO Roundtrip Tests for Data Preservation**

**Missing Test Pattern**:
```python
def test_sync_creatives_preserves_user_provided_urls():
    """Verify user URLs survive sync→store→retrieve→use flow."""
    # 1. Sync creative with user URL in AdCP format
    user_url = "https://cdn.client.com/banner.png"
    sync_result = sync_creatives([{
        "creative_id": "test-123",
        "format_id": "display_300x250",  # Format requiring preview
        "assets": {
            "banner_image": {"url": user_url},  # AdCP format
            "click_url": {"url": "https://client.com/landing"}
        }
    }])

    # 2. Retrieve from database
    retrieved = list_creatives()

    # 3. Verify user URL preserved (NOT preview URL)
    assert retrieved[0].assets["banner_image"]["url"] == user_url  # ❌ Currently fails!
```

**Gap**: No tests verify data preservation through full lifecycle.

**Impact**: **CRITICAL** - Tests execute code but don't validate semantic correctness.

#### C. **NO Tests Using Cached Format Specs**

**Current State**:
- Tests use hardcoded format IDs like `"display_300x250"`
- Tests mock format objects with generic structures
- NO tests load formats from `schemas/v1/formats/` cache
- NO tests verify asset IDs match format spec (e.g., `banner_image` for banner formats)

**Gap**: Tests don't use real format specs from creative agents.

**Impact**: **HIGH** - Missing format-specific asset structure validation.

#### D. **NO Integration Tests for Preview→Storage Flow**

**Missing Test**:
```python
def test_preview_generation_preserves_user_assets():
    """Verify preview_creative doesn't overwrite user-provided assets."""
    # Setup: Real format requiring preview, user provides URL
    # Expected: Preview generated for validation, user URL preserved
    # Actual: Preview URL overwrites user URL
```

**Gap**: Preview generation path not tested with real asset structures.

**Impact**: **CRITICAL** - Core bug is in this exact flow.

### What Tests Are Misleading

#### E. **Over-Mocking Hides Real Behavior**

**Example**: `tests/integration/test_generative_creatives.py`
```python
mock_registry.preview_creative = AsyncMock(
    return_value={
        "previews": [{"renders": [{"preview_url": "..."}]}]
    }
)
```

**Problem**:
- Mock returns preview URL
- Code overwrites user URL with preview URL
- Test checks creative was created (passes ✓)
- **But never verifies which URL is stored** (data corruption missed!)

**Impact**: **HIGH** - Tests pass while bug exists because mocks hide behavior.

#### F. **Schema Tests Don't Test Data Flow**

**Example**: `tests/unit/test_sync_creatives_assignment_reporting.py`
```python
def test_sync_creative_result_has_assignment_fields():
    result = SyncCreativeResult(
        creative_id="test_creative_1",
        action="created",
        assigned_to=["pkg_1", "pkg_2"],
    )
    assert result.assigned_to == ["pkg_1", "pkg_2"]  # Tests schema, not behavior
```

**Problem**: Tests schema structure (fields exist), not data correctness (values preserved).

**Impact**: **MEDIUM** - False confidence from passing schema tests.

---

## 4. Would Coverage Metrics Have Helped?

### Coverage Analysis

**Line 617 (Buggy Code)**:
```python
if first_render.get("preview_url"):
    data["url"] = first_render["preview_url"]  # 🐛 Line 617
```

**Coverage Status**: ✅ **COVERED** (but behavior not tested!)

**Evidence**:
- `test_generative_creatives.py` mocks preview_creative
- Mock returns `preview_url`
- Line 617 executes during test
- **Coverage report shows 100% for this line**

### Why Coverage Failed Us

**Coverage tells you**:
- ✅ This line executed
- ✅ No exceptions raised
- ✅ Function returned

**Coverage does NOT tell you**:
- ❌ User data was preserved
- ❌ Correct URL is stored
- ❌ Behavior matches specification

### The Illusion of Safety

```
Coverage Report:
src/core/tools/creatives.py    98%    ✓
  Line 617:                    COVERED ✓

Test Results:
✓ test_generative_format_detection_calls_build_creative
✓ test_static_format_calls_preview_creative
All tests passed!

Reality:
🐛 Line 617 silently corrupts user data
🐛 User URLs overwritten with preview URLs
🐛 No test validates data preservation
```

**Conclusion**: **Coverage metrics are MISLEADING** for data transformation bugs.

---

## 5. Root Cause Analysis

### Why Did This Happen?

#### A. **Architectural Issue: Mixed Responsibilities**

**Problem**: `sync_creatives` does too much:
1. Schema validation
2. Asset extraction
3. Preview generation (for validation)
4. Preview storage (for UI)
5. Data persistence

**Result**: Data flows through multiple transformations, easy to lose track.

**Recommendation**: Separate concerns:
- `extract_assets()` - Parse AdCP asset structures
- `validate_creative()` - Call preview_creative for validation
- `store_creative()` - Persist user data (NOT preview data)
- `generate_preview()` - Create preview for UI (separate from storage)

#### B. **Testing Methodology: Wrong Abstractions**

**Problem**: Tests mock at wrong boundaries:
- Mock `preview_creative` (hides overwrite)
- Mock database (hides storage corruption)
- Mock format specs (hides real structures)

**Result**: Integration bugs slip through unit tests.

**Recommendation**: Test at correct boundaries:
- **Unit tests**: Extract logic, schema parsing (NO database, NO network)
- **Integration tests**: Full flow with real database, mock only external APIs
- **E2E tests**: Real format specs from cache, real database

#### C. **Missing Specification Tests**

**Problem**: No tests verify AdCP spec compliance for asset structures.

**Example Missing Test**:
```python
def test_banner_format_uses_banner_image_asset():
    """Verify banner formats use correct asset ID per spec."""
    format_spec = load_format_spec("display_300x250")  # From cache
    assert "banner_image" in format_spec.required_assets

    # Verify sync_creatives extracts from correct asset ID
    result = sync_creatives([{
        "format_id": "display_300x250",
        "assets": {format_spec.required_assets[0]: {"url": "..."}}
    }])
    assert result.success
```

**Recommendation**: Add contract tests for format specs.

#### D. **No Mutation Testing**

**Problem**: Tests verify code executes, not that it does the right thing.

**Example**: Mutation testing would catch this:
```python
# Original (buggy):
data["url"] = first_render["preview_url"]

# Mutant 1 (breaks tests if they check data preservation):
# data["url"] = data.get("url", first_render["preview_url"])

# Mutant 2 (breaks tests if they check URL source):
# data["preview_url"] = first_render["preview_url"]  # Different key!
```

**If tests still pass with these mutations** → Tests don't validate behavior!

**Recommendation**: Consider mutation testing for critical data paths.

---

## 6. Specific Test Cases to Add

### Immediate Priority (Fix the Bug)

#### Test 1: AdCP Asset Structure Preservation
```python
@pytest.mark.integration
@pytest.mark.requires_db
def test_sync_creatives_preserves_adcp_asset_urls():
    """CRITICAL: Verify user URLs in AdCP format survive preview generation.

    This test catches the bug where preview_url overwrites user-provided URLs.
    """
    # Setup: Format requiring preview (from cache)
    format_spec = load_cached_format("display_300x250")

    # User provides URL in AdCP format
    user_banner_url = "https://cdn.advertiser.com/summer-sale-banner.png"
    user_click_url = "https://advertiser.com/landing"

    # Sync creative (triggers preview generation)
    result = sync_creatives([{
        "creative_id": "test-preserve-url",
        "name": "Summer Sale Banner",
        "format_id": "display_300x250",
        "assets": {
            "banner_image": {"url": user_banner_url},  # AdCP format!
            "click_url": {"url": user_click_url}
        }
    }])

    assert result.created_count == 1

    # Retrieve from database
    creatives = list_creatives()
    creative = next(c for c in creatives if c.creative_id == "test-preserve-url")

    # CRITICAL ASSERTIONS
    assert creative.assets["banner_image"]["url"] == user_banner_url, \
        f"User banner URL overwritten! Expected {user_banner_url}, got {creative.assets['banner_image']['url']}"

    assert creative.assets["click_url"]["url"] == user_click_url, \
        f"User click URL overwritten!"

    # Preview should be stored separately (NOT overwrite user URL)
    assert creative.data["preview_response"] is not None, "Preview not stored"
    preview_url = creative.data["preview_response"]["previews"][0]["renders"][0]["preview_url"]
    assert preview_url != user_banner_url, "Preview URL same as user URL (suspicious)"
```

#### Test 2: Roundtrip Validation
```python
@pytest.mark.integration
@pytest.mark.requires_db
def test_creative_data_roundtrip_with_preview():
    """Verify creative data survives: sync → preview → store → retrieve → adapter use."""
    user_url = "https://cdn.client.com/video.mp4"

    # 1. Sync with user URL
    sync_creatives([{
        "creative_id": "roundtrip-test",
        "format_id": "video_preroll",
        "assets": {"video_asset": {"url": user_url}}
    }])

    # 2. Retrieve from database
    creative = list_creatives()[0]

    # 3. Verify user URL preserved
    assert creative.assets["video_asset"]["url"] == user_url

    # 4. Simulate adapter using creative (should get user URL, not preview)
    adapter_asset = _convert_creative_to_adapter_asset(creative)
    assert adapter_asset["url"] == user_url, "Adapter would upload wrong URL!"
```

#### Test 3: Format-Specific Asset IDs
```python
@pytest.mark.integration
@pytest.mark.requires_db
@pytest.mark.parametrize("format_id,asset_role,url", [
    ("display_300x250", "banner_image", "https://example.com/banner.png"),
    ("video_preroll", "video_asset", "https://example.com/video.mp4"),
    ("native_article", "headline", "https://example.com/article"),
    ("audio_preroll", "audio_asset", "https://example.com/audio.mp3"),
])
def test_format_specific_asset_ids_preserved(format_id, asset_role, url):
    """Verify format-specific asset IDs are correctly extracted and preserved."""
    result = sync_creatives([{
        "creative_id": f"test-{format_id}",
        "format_id": format_id,
        "assets": {asset_role: {"url": url}}
    }])

    # Retrieve and verify
    creative = list_creatives()[0]
    assert creative.assets[asset_role]["url"] == url, \
        f"Asset URL for {asset_role} not preserved in {format_id} format"
```

### High Priority (Prevent Regressions)

#### Test 4: Preview Generation Without User URL
```python
def test_preview_generated_when_no_user_url():
    """Verify preview URL is used ONLY when user provides no URL."""
    # User provides NO URL (preview should be used)
    result = sync_creatives([{
        "creative_id": "no-user-url",
        "format_id": "display_300x250",
        "assets": {"targeting": {"age": "18-34"}}  # No banner_image
    }])

    creative = list_creatives()[0]
    # Should have preview URL since no user URL provided
    assert creative.data["url"].startswith("https://preview.")
```

#### Test 5: Generative Creative URL Preservation
```python
def test_generative_format_preserves_user_context():
    """Verify generative formats preserve user context, don't overwrite with output."""
    result = sync_creatives([{
        "creative_id": "gen-test",
        "format_id": "display_300x250_generative",
        "assets": {
            "message": {"content": "Generate banner for eco products"},
            "brand_logo": {"url": "https://brand.com/logo.png"}  # User asset
        }
    }])

    creative = list_creatives()[0]
    # Generative output should be stored separately
    assert creative.data["generative_build_result"] is not None
    # User-provided assets should be preserved
    assert creative.assets["brand_logo"]["url"] == "https://brand.com/logo.png"
```

### Medium Priority (Architecture Improvements)

#### Test 6: Preview vs Storage Separation
```python
def test_preview_stored_separately_from_user_data():
    """Verify preview data stored in separate field, not overwriting user data."""
    user_url = "https://cdn.com/creative.png"

    sync_creatives([{
        "creative_id": "sep-test",
        "format_id": "display_300x250",
        "assets": {"banner_image": {"url": user_url}}
    }])

    creative = list_creatives()[0]

    # User URL in assets
    assert creative.assets["banner_image"]["url"] == user_url

    # Preview in separate field
    assert "preview_response" in creative.data
    preview = creative.data["preview_response"]["previews"][0]["renders"][0]

    # They should be different!
    assert preview["preview_url"] != user_url, \
        "Preview URL shouldn't match user URL (indicates one overwrote other)"
```

---

## 7. Pre-Commit Hook Recommendations

### New Hooks to Add

#### Hook 1: Detect Unconditional Data Overwrites
```python
# .git/hooks/pre-commit.d/check-data-overwrites.py
"""Detect unconditional overwrites of user data."""

RISKY_PATTERNS = [
    r'data\["(\w+)"\]\s*=\s*\w+\.get\(',  # data["url"] = obj.get("url")
    r'data\["(\w+)"\]\s*=\s*\w+\["(\w+)"\]',  # data["url"] = result["preview_url"]
]

ALLOWED_PATTERNS = [
    r'if\s+.*data\.get\(',  # if ... data.get() - conditional
    r'data\.get\("(\w+)",\s*default',  # data.get("url", default) - has fallback
]

def check_file(filepath):
    """Check file for risky data overwrites."""
    with open(filepath) as f:
        for i, line in enumerate(f, 1):
            for pattern in RISKY_PATTERNS:
                if re.search(pattern, line):
                    # Check if it's in a conditional block
                    if not any(re.search(allow, line) for allow in ALLOWED_PATTERNS):
                        print(f"{filepath}:{i} - Unconditional data overwrite detected")
                        print(f"  {line.strip()}")
                        print("  Consider: if not data.get('field'): data['field'] = ...")
                        return False
    return True
```

#### Hook 2: Require Roundtrip Tests for Data Handlers
```python
# .git/hooks/pre-commit.d/require-roundtrip-tests.py
"""Require roundtrip tests for functions that modify data."""

DATA_HANDLER_PATTERNS = [
    r'def\s+(_sync_creatives_impl|_list_creatives_impl)',
    r'def\s+.*_store_.*\(',
    r'def\s+.*_transform_.*\(',
]

def check_test_coverage(source_file, test_dir):
    """Verify data handlers have roundtrip tests."""
    # Find data handler functions
    handlers = []
    with open(source_file) as f:
        for line in f:
            for pattern in DATA_HANDLER_PATTERNS:
                if match := re.search(pattern, line):
                    handlers.append(match.group(1))

    # Check for roundtrip tests
    for handler in handlers:
        test_pattern = f"test_{handler}_.*roundtrip|test_roundtrip.*{handler}"
        if not glob.glob(f"{test_dir}/**/*{handler}*roundtrip*.py"):
            print(f"Missing roundtrip test for {handler}")
            print(f"Add: test_{handler}_data_preservation_roundtrip()")
            return False
    return True
```

#### Hook 3: Verify AdCP Format Spec Usage
```python
# .git/hooks/pre-commit.d/check-adcp-format-usage.py
"""Ensure tests use real AdCP format specs."""

def check_test_file(filepath):
    """Check if creative tests use real format specs."""
    if "creative" not in filepath or "test_" not in filepath:
        return True

    with open(filepath) as f:
        content = f.read()

        # Check if test uses creatives
        if "sync_creatives" in content or "list_creatives" in content:
            # Must load format specs from cache
            if "load_cached_format" not in content and "schemas/v1" not in content:
                print(f"{filepath} - Tests should use cached format specs")
                print("  from tests.utils.format_helpers import load_cached_format")
                print("  format_spec = load_cached_format('display_300x250')")
                return False

    return True
```

---

## 8. Coverage Strategy Improvements

### What Coverage Can't Catch

**Data Transformation Bugs**:
- ❌ Coverage shows line executed
- ❌ Doesn't show if correct data stored
- ❌ Doesn't show if user data preserved
- ❌ Doesn't show if spec compliance maintained

**Integration Issues**:
- ❌ Unit test coverage hides integration bugs
- ❌ Mocked tests pass while real flow fails
- ❌ Database storage corruption not detected

### What We Need Instead

#### A. **Behavioral Coverage** (Not Line Coverage)

**Metric**: % of user journeys tested end-to-end

**Example**:
```
User Journey: Sync creative with AdCP asset structure
- [ ] User provides URL in assets.banner_image.url
- [ ] Creative synced successfully
- [ ] Preview generated (validation)
- [ ] User URL preserved in database
- [ ] Preview stored separately
- [ ] Adapter receives user URL (not preview)
- [ ] Creative displays correctly in ad server
```

**Coverage**: 0/7 steps tested → 0% behavioral coverage

#### B. **Contract Testing** (Format Specs)

**Test**: Each format spec has matching test

```bash
# schemas/v1/formats/display_300x250.json exists
# tests/unit/test_format_display_300x250.py must exist
# tests/integration/test_format_display_300x250_roundtrip.py must exist
```

#### C. **Mutation Testing** (Correctness)

**Tool**: `mutmut` or `cosmic-ray`

**Example**:
```python
# Original
data["url"] = user_url

# Mutant 1: Wrong key
data["preview_url"] = user_url  # Should break tests!

# Mutant 2: Wrong value
data["url"] = preview_url  # Should break tests!

# If tests still pass → Tests are incomplete!
```

#### D. **Property-Based Testing** (Edge Cases)

**Tool**: `hypothesis`

**Example**:
```python
from hypothesis import given, strategies as st

@given(
    format_id=st.sampled_from(list_all_format_ids()),
    asset_role=st.text(min_size=1),
    url=st.urls()
)
def test_any_asset_structure_preserved(format_id, asset_role, url):
    """Property: User URLs always preserved, regardless of structure."""
    result = sync_creatives([{
        "format_id": format_id,
        "assets": {asset_role: {"url": url}}
    }])

    retrieved = list_creatives()[0]
    assert retrieved.assets[asset_role]["url"] == url
```

---

## 9. Prevention Strategy

### Immediate Actions (Week 1)

1. **Fix the bug** (lines 617, 969, 536)
   - Add conditional: `if not data.get("url"): data["url"] = preview_url`
   - Store preview separately: `data["preview_url"] = preview_url`

2. **Add critical tests** (Test 1-3 above)
   - Test AdCP asset structure preservation
   - Test roundtrip validation
   - Test format-specific asset IDs

3. **Add pre-commit hook** (Hook 1)
   - Detect unconditional data overwrites
   - Flag suspicious patterns for review

### Short-Term Actions (Month 1)

4. **Audit similar patterns**
   - Review all `data["field"] = value` assignments
   - Check for other unconditional overwrites
   - Verify conditional logic exists

5. **Add architecture tests**
   - Test preview vs storage separation
   - Test adapter receives correct URLs
   - Test UI receives preview URLs

6. **Improve test infrastructure**
   - Create `load_cached_format()` helper
   - Create `assert_roundtrip_preserves()` helper
   - Add format spec fixtures

### Long-Term Actions (Quarter 1)

7. **Implement behavioral coverage**
   - Define user journeys
   - Track journey coverage
   - Target 100% critical journey coverage

8. **Add mutation testing**
   - Configure `mutmut` for critical paths
   - Require 80%+ mutation score
   - Integrate into CI

9. **Refactor architecture**
   - Separate preview generation from storage
   - Extract asset parsing to dedicated module
   - Clear separation of concerns

10. **Contract testing framework**
    - Auto-generate tests from format specs
    - Verify schema compliance
    - Test format-specific behaviors

---

## 10. Conclusion

### Key Findings

1. **Bug root cause**: Unconditional overwrite of user data with API response
2. **Test gap**: No tests use AdCP-compliant asset structures
3. **Coverage misleading**: Line executed ≠ behavior tested
4. **Similar patterns**: 3 other high-risk overwrites found
5. **Architecture issue**: Mixed responsibilities hide data flow

### Critical Recommendations

**Must Do Now**:
- Fix bugs on lines 617, 969, 536
- Add Test 1 (asset preservation)
- Add Test 2 (roundtrip validation)
- Add Hook 1 (detect overwrites)

**Should Do Soon**:
- Implement behavioral coverage
- Add mutation testing
- Refactor preview generation
- Create format spec test framework

**Long-Term Goals**:
- 100% critical journey coverage
- 80%+ mutation score
- Architectural separation of concerns
- Automated contract testing

### Would Coverage Have Helped?

**Answer**: **NO**

**Reason**:
- Buggy line was covered (executed in tests)
- Tests passed while bug existed
- Coverage shows execution, not correctness
- Integration bugs need integration tests, not coverage

**What Would Have Helped**:
1. ✅ Roundtrip tests (verify data preservation)
2. ✅ Real format specs in tests (catch structure bugs)
3. ✅ Behavioral coverage (test user journeys)
4. ✅ Mutation testing (test correctness)
5. ✅ Contract tests (verify spec compliance)

---

## Appendix: File Locations

### Buggy Code
- `src/core/tools/creatives.py:617` - UPDATE path (preview overwrite)
- `src/core/tools/creatives.py:969` - CREATE path (preview overwrite)
- `src/core/tools/creatives.py:536` - UPDATE path (generative overwrite)
- `src/core/tools/creatives.py:896` - CREATE path (generative overwrite)

### Test Files to Create
- `tests/integration/test_creative_asset_preservation.py` (Test 1-3)
- `tests/integration/test_creative_roundtrip.py` (Test 2, 6)
- `tests/unit/test_format_specs_compliance.py` (Test 3, Contract tests)

### Hook Files to Create
- `.git/hooks/pre-commit.d/check-data-overwrites.py`
- `.git/hooks/pre-commit.d/require-roundtrip-tests.py`
- `.git/hooks/pre-commit.d/check-adcp-format-usage.py`

### Helper Files to Create
- `tests/utils/format_helpers.py` - `load_cached_format()`
- `tests/utils/assertion_helpers.py` - `assert_roundtrip_preserves()`
- `tests/fixtures/format_specs.py` - Format spec fixtures

---

**Report End**
