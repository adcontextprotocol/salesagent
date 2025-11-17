# Embedded Types Audit - AdCP Library Alignment

**Date**: 2025-11-17
**Context**: Following the ListCreativeFormatsRequest/Response refactoring pattern (commit: refactor list_creative_formats to extend library types), systematically audit ALL embedded types in `src/core/schemas.py` to ensure they properly extend adcp library types.

## Available Library Types (adcp 2.1.0)

From `adcp.types.generated`:
- **CreativeAsset** - Individual creative with assets
- **CreativeManifest** - Creative template/manifest for generative formats
- **Format** - Format definition with requirements
- **FormatId** - Namespaced format identifier
- **Package** - Response schema (has package_id, status)
- **PackageRequest** - Request schema (for creating media buys)
- **Product** - Product offering with formats/pricing
- **Targeting** (TargetingOverlay) - Targeting criteria
- **SyncCreativesRequest** - Request to sync creative assets
- **SyncCreativesResponse** - Response from syncing creatives
- **ListCreativesRequest** - Request to list/search creatives
- **ListCreativesResponse** - Response from listing creatives
- **BrandManifest** - Brand information
- **Property** - Publisher property

## Current State Analysis

### ✅ Already Refactored (Extend Library Types)

1. **Product** (line 329) - Extends `LibraryProduct`
   - Internal fields: `tenant_id`, `implementation_config` (both marked `exclude=True`)
   - Status: ✅ CORRECT

2. **Format** (line 427) - Extends `LibraryFormat`
   - Internal fields: `tenant_id`, `created_at`, `updated_at` (all marked `exclude=True`)
   - Status: ✅ CORRECT

3. **FormatId** (line 385) - Extends `LibraryFormatId`
   - No internal fields
   - Status: ✅ CORRECT

4. **Package** (line 2428) - Extends `LibraryPackage`
   - Internal fields: `tenant_id`, `media_buy_id`, `platform_line_item_id`, `created_at`, `updated_at`, `metadata`, `pricing_model` (all marked `exclude=True`)
   - Has `model_dump_internal()` to include internal fields
   - Status: ✅ CORRECT

5. **PackageRequest** (line 2374) - Extends `LibraryPackageRequest`
   - Internal fields: `tenant_id`, `metadata`, `pricing_model`, `products`, `impressions` (all marked `exclude=True`)
   - Legacy field support: `creatives`
   - Status: ✅ CORRECT

6. **ListCreativeFormatsRequest** (line 590) - Extends `LibraryListCreativeFormatsRequest`
   - No internal fields
   - Status: ✅ CORRECT (recent refactoring)

7. **ListCreativeFormatsResponse** (line 627) - Extends `LibraryListCreativeFormatsResponse`
   - No internal fields
   - Status: ✅ CORRECT (recent refactoring)

### 🔄 NEEDS REFACTORING (Should Extend Library Types)

#### 1. **Creative** (line 1569) - Should extend `CreativeAsset`

**Current Implementation:**
```python
class Creative(AdCPBaseModel):
    # AdCP v1 spec fields
    creative_id: str
    name: str
    format: FormatId = Field(alias="format_id")
    assets: dict[str, dict[str, Any]]

    # Optional
    inputs: list[dict[str, Any]] | None
    tags: list[str] | None
    approved: bool | None

    # Internal fields
    principal_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: str = Field(default="pending")
```

**Library CreativeAsset Fields:**
```python
class CreativeAsset:
    creative_id: str  # Required
    name: str  # Required
    format_id: FormatId  # Required
    assets: dict[str, Union[ImageAsset, VideoAsset, ...]]  # Required, typed union

    # Optional
    approved: bool | None
    inputs: list[Input] | None  # Typed Input objects
    tags: list[str] | None
```

**Compatibility:**
- ✅ Fields match well
- ⚠️ `assets` is typed in library (union of specific asset types), we use `dict[str, Any]`
- ⚠️ `inputs` is typed in library (list[Input]), we use `list[dict[str, Any]]`
- ⚠️ Library uses `format_id`, we alias it as `format` with property getter

**Refactoring Strategy:**
```python
from adcp.types.generated import CreativeAsset as LibraryCreativeAsset

class Creative(LibraryCreativeAsset):
    """Extends library CreativeAsset with internal fields."""

    # Internal fields (not in AdCP spec) - marked with exclude=True
    principal_id: str | None = Field(None, exclude=True)
    created_at: datetime | None = Field(None, exclude=True)
    updated_at: datetime | None = Field(None, exclude=True)
    status: str = Field(default="pending", exclude=True)

    # Keep alias and property for backward compatibility
    @property
    def format_id(self) -> str:
        return self.format_id.id
```

**Issues:**
- Library's `assets` field is strictly typed (specific asset types), ours is `dict[str, Any]`
- May need to maintain our looser typing for backward compatibility

**Decision:** ⚠️ REVIEW CAREFULLY - Asset typing may be too strict for our use case

---

#### 2. **SyncCreativesRequest** (line 1750) - Library type exists

**Current Implementation:**
```python
class SyncCreativesRequest(AdCPBaseModel):
    creatives: list[Creative]  # Uses our Creative, not library CreativeAsset
    context: dict[str, Any] | None
    patch: bool = False
    assignments: dict[str, list[str]] | None
    delete_missing: bool = False
    dry_run: bool = False
    validation_mode: Literal["strict", "lenient"] = "strict"
    push_notification_config: dict[str, Any] | None
```

**Library SyncCreativesRequest Fields:**
```python
class SyncCreativesRequest:
    creatives: list[CreativeAsset]  # Uses library CreativeAsset
    context: dict[str, Any] | None
    patch: bool | None
    assignments: dict[str, list[str]] | None
    delete_missing: bool | None
    dry_run: bool | None
    validation_mode: Literal["strict", "lenient"] | None
    push_notification_config: PushNotificationConfig | None
```

**Compatibility:**
- ✅ Fields match well
- ⚠️ Library uses `CreativeAsset`, we use our `Creative`
- ⚠️ All boolean fields are optional in library (`bool | None`), we have defaults
- ⚠️ `push_notification_config` is typed in library (`PushNotificationConfig`), we use `dict[str, Any]`

**Refactoring Strategy:**
```python
from adcp.types.generated import SyncCreativesRequest as LibrarySyncCreativesRequest

class SyncCreativesRequest(LibrarySyncCreativesRequest):
    """Extends library SyncCreativesRequest - no internal fields needed."""

    # Note: Uses Creative instead of library's CreativeAsset due to implementation differences
    # (our Creative has internal fields like principal_id, status)
    creatives: list[Creative]  # Override to use our Creative type
```

**Issues:**
- We use our `Creative` type (with internal fields), library uses `CreativeAsset`
- If we refactor `Creative` to extend `CreativeAsset`, this becomes simpler

**Decision:** ✅ CAN EXTEND - Keep our Creative override for now

---

#### 3. **ListCreativesRequest** (line 1969) - Library type exists

**Current Implementation:**
```python
class ListCreativesRequest(AdCPBaseModel):
    # Convenience fields (not in library spec)
    media_buy_id: str | None
    buyer_ref: str | None
    status: str | None
    format: str | None
    tags: list[str] | None
    created_after: datetime | None
    created_before: datetime | None
    search: str | None

    # AdCP spec fields (match library)
    context: dict[str, Any] | None
    filters: dict[str, Any] | None
    pagination: dict[str, Any] | None
    sort: dict[str, Any] | None
    fields: list[str] | None
    include_performance: bool = False
    include_assignments: bool = False
    include_sub_assets: bool = False

    # Convenience pagination/sorting fields
    page: int = 1
    limit: int = 50
    sort_by: str | None = "created_date"
    sort_order: Literal["asc", "desc"] = "desc"
```

**Library ListCreativesRequest Fields:**
```python
class ListCreativesRequest:
    context: dict[str, Any] | None
    filters: dict[str, Any] | None  # This is where our convenience fields should map
    pagination: dict[str, Any] | None
    sort: dict[str, Any] | None
    fields: list[str] | None
    include_performance: bool | None
    include_assignments: bool | None
    include_sub_assets: bool | None
```

**Compatibility:**
- ⚠️ We have many convenience fields (`media_buy_id`, `buyer_ref`, etc.) that don't exist in library
- ⚠️ Library uses `filters` dict for filtering, we have individual fields
- ⚠️ Library uses `pagination` dict, we have `page`/`limit` fields
- ⚠️ Library uses `sort` dict, we have `sort_by`/`sort_order` fields

**Refactoring Strategy:**
**CANNOT EXTEND** - Too many convenience fields that don't map to library structure.

**Decision:** ❌ DO NOT EXTEND - Our convenience fields are implementation-specific. Document why in docstring:
```python
class ListCreativesRequest(AdCPBaseModel):
    """Request to list and search creative library (AdCP spec compliant).

    NOTE: Does not extend library type due to significant differences in convenience fields.
    Our implementation provides convenience fields (media_buy_id, buyer_ref, etc.) that are
    mapped to the library's `filters` structure internally.
    """
```

---

#### 4. **SyncCreativesResponse** (line 1890) - Library type exists

**Current Implementation:**
```python
class SyncCreativesResponse(AdCPBaseModel):
    creatives: list[SyncCreativeResult]
    context: dict[str, Any] | None
    dry_run: bool | None

    # Has @model_serializer for nested serialization
```

**Library SyncCreativesResponse Structure:**
Library uses discriminated union pattern (RootModel with variants):
- **SyncCreativesResponse** (RootModel) - Wraps union of:
  - **SyncCreativesResponse1** (success) - Has `creatives`, `context`, `dry_run`
  - **SyncCreativesResponse2** (error) - Has `errors`, `context`

Library SyncCreativesResponse1 fields:
- `context: dict[str, Any] | None`
- `creatives: list[Creative]` - Where Creative has:
  - `creative_id: str`
  - `action: Action` (enum: created, updated, unchanged, failed, deleted)
  - `platform_id: str | None`
  - `changes: list[str] | None`
  - `errors: list[str] | None`
  - `warnings: list[str] | None`
  - `assigned_to: list[str] | None`
  - `assignment_errors: dict[str, str] | None`
  - `expires_at: datetime | None`
  - `preview_url: AnyUrl | None`
- `dry_run: bool | None`

**Our SyncCreativeResult fields:**
```python
class SyncCreativeResult:
    creative_id: str
    action: Literal["created", "updated", "unchanged", "failed", "deleted"]
    status: str | None  # Internal field
    platform_id: str | None
    changes: list[str]
    errors: list[str]
    warnings: list[str]
    review_feedback: str | None  # Internal field
    assigned_to: list[str] | None
    assignment_errors: dict[str, str] | None
```

**Compatibility Analysis:**
- ✅ Top-level fields match (creatives, context, dry_run)
- ⚠️ Library uses RootModel discriminated union (success vs error variants)
- ✅ Our `SyncCreativeResult` is very close to library's `Creative` nested type
- ⚠️ We have internal fields: `status`, `review_feedback` (excluded via model_dump)
- ⚠️ Library has additional fields: `expires_at`, `preview_url`
- ❌ Extending RootModel is complex and breaks our response pattern

**Refactoring Strategy:**
**DO NOT EXTEND** - Library uses RootModel discriminated union which is incompatible with our response pattern.
We intentionally use non-discriminated responses to allow protocol envelope wrapping.

**Decision:** ❌ DO NOT EXTEND - Keep our implementation. Library's RootModel pattern is incompatible with protocol envelope wrapper pattern. Our nested `SyncCreativeResult` already excludes internal fields properly.

---

#### 5. **ListCreativesResponse** (line 2034) - Library type exists

**Current Implementation:**
```python
class ListCreativesResponse(AdCPBaseModel):
    context: dict[str, Any] | None
    query_summary: QuerySummary
    pagination: Pagination
    creatives: list[Creative]
    format_summary: dict[str, int] | None
    status_summary: dict[str, int] | None

    # Has @model_serializer for nested serialization
```

**Library ListCreativesResponse Structure:**
```python
class ListCreativesResponse:
    context: dict[str, Any] | None
    query_summary: QuerySummary  # Nested type with filters_applied, returned, sort_applied, total_matching
    pagination: Pagination  # Nested type with current_page, has_more, limit, offset, total_pages
    creatives: list[Creative]  # Full creative with assets, status, performance, etc.
    format_summary: dict[str, int] | None
    status_summary: StatusSummary | None  # Typed object with approved, archived, pending_review, rejected fields
```

**Our nested types:**
- `QuerySummary`: Fields match library (total_matching, returned, filters_applied, sort_applied)
- `Pagination`: Fields match library (limit, offset, has_more, total_pages, current_page)
- `Creative`: Our Creative is different (internal fields: principal_id, status, created_at, updated_at)
- `status_summary`: We use `dict[str, int] | None`, library uses typed `StatusSummary` object

**Compatibility Analysis:**
- ✅ Top-level fields match well
- ✅ Our nested `QuerySummary` matches library structure
- ✅ Our nested `Pagination` matches library structure
- ⚠️ Library uses typed `StatusSummary`, we use `dict[str, int]`
- ⚠️ Library's nested `Creative` is different from ours (has legacy fields: media_url, width, height, click_url)
- ❌ We use our `Creative` type (with internal fields), library expects different structure

**Refactoring Strategy:**
**DO NOT EXTEND** - Library's nested Creative type is legacy format (media_url, width, height) which conflicts with our AdCP v1 spec-compliant Creative (format_id + assets).

**Decision:** ❌ DO NOT EXTEND - Keep our implementation. Our Creative type is AdCP v1 spec-compliant (assets-based), while library's nested Creative in ListCreativesResponse is legacy format. Our nested serialization already works correctly.

---

### ✅ ALREADY CORRECT (Don't Need Library Extension)

These types are internal or don't have corresponding library types:

1. **CreativeAdaptation** (line 1662) - Internal creative suggestion type
2. **CreativeStatus** (line 1675) - Internal creative status tracking
3. **CreativeAssignment** (line 1683) - Internal creative-package mapping
4. **SyncSummary** (line 1789) - Internal sync summary (nested in response)
5. **SyncCreativeResult** (line 1800) - Internal sync result (nested in response)
6. **AssignmentsSummary** (line 1864) - Internal assignments summary
7. **AssignmentResult** (line 1875) - Internal assignment result
8. **QuerySummary** (line 2015) - Internal query summary (nested in response)
9. **Pagination** (line 2024) - Internal pagination info (nested in response)
10. **BrandManifest** (line 2314) - We have a legacy version, but library type exists
11. **BrandManifestRef** (line 2343) - Internal wrapper (not in library)

## Final Conclusions

### ✅ Already Properly Extended (7 types)
1. **Product** - Extends `LibraryProduct` with internal fields
2. **Format** - Extends `LibraryFormat` with internal fields
3. **FormatId** - Extends `LibraryFormatId` (no internal fields)
4. **Package** - Extends `LibraryPackage` with internal fields
5. **PackageRequest** - Extends `LibraryPackageRequest` with internal fields
6. **ListCreativeFormatsRequest** - Extends `LibraryListCreativeFormatsRequest`
7. **ListCreativeFormatsResponse** - Extends `LibraryListCreativeFormatsResponse`

### ❌ Cannot Extend (Documented Reasons)
1. **ListCreativesRequest** - Has convenience fields that don't map to library structure (docstring already explains)
2. **SyncCreativesResponse** - Library uses RootModel discriminated union incompatible with our protocol envelope pattern
3. **ListCreativesResponse** - Library's nested Creative is legacy format (media_url/width/height), ours is AdCP v1 spec-compliant (assets-based)

### ⚠️ Questionable Extension (Needs Careful Analysis)
1. **Creative** - Library `CreativeAsset` has strictly typed assets, ours uses `dict[str, Any]` for flexibility
   - **Risk**: Strict typing may break existing code
   - **Benefit**: Type safety and library alignment
   - **Recommendation**: Keep as-is for now, our implementation is AdCP v1 spec-compliant

2. **SyncCreativesRequest** - Could extend but would need to override `creatives` field
   - **Current**: Uses our `Creative` type
   - **Library**: Uses library `CreativeAsset` type
   - **Recommendation**: Keep as-is since it depends on Creative extension decision

### ✅ Correctly Independent (10 types)
These are internal implementation types without library equivalents:
1. **CreativeAdaptation** - Internal creative suggestion type
2. **CreativeStatus** - Internal creative status tracking
3. **CreativeAssignment** - Internal creative-package mapping
4. **SyncSummary** - Internal sync summary (nested)
5. **SyncCreativeResult** - Internal sync result (nested, excludes internal fields correctly)
6. **AssignmentsSummary** - Internal assignments summary
7. **AssignmentResult** - Internal assignment result
8. **QuerySummary** - Internal query summary (nested, matches library structure)
9. **Pagination** - Internal pagination info (nested, matches library structure)
10. **BrandManifestRef** - Internal wrapper

## Recommendations

### HIGH PRIORITY ✅ COMPLETED
1. ✅ **Document non-extendable types** - Added docstring to `ListCreativesRequest`
2. ✅ **Investigate library response types** - Analyzed discriminated unions, documented incompatibilities
3. ✅ **Create comprehensive audit** - This document

### MEDIUM PRIORITY
4. **Verify current extensions work** - Run contract tests to ensure existing 7 extensions are compliant
5. **Add docstrings to response types** - Document why `SyncCreativesResponse` and `ListCreativesResponse` don't extend library

### LOW PRIORITY (Not Recommended)
6. ~~**Investigate Creative extension**~~ - Keep as-is. Our Creative is AdCP v1 spec-compliant with flexible assets typing
7. ~~**Extend SyncCreativesRequest**~~ - Keep as-is. Depends on Creative, no immediate benefit

## Testing Strategy

After each refactoring:
1. Run AdCP contract tests: `pytest tests/unit/test_adcp_contract.py -v`
2. Run integration tests: `pytest tests/integration/ -x`
3. Verify nested serialization excludes internal fields
4. Check backward compatibility with existing code

## Next Steps

1. ✅ Create this audit document
2. ⚠️ Add docstring to `ListCreativesRequest` explaining non-extension
3. ⚠️ Investigate library response types structure
4. ⚠️ Decide on `Creative` refactoring approach
5. ✅ Update `adcp_factories.py` to use library types consistently
6. ✅ Run full test suite to verify no regressions
