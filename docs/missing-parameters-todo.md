# Missing Optional Parameters - Future Work

This document tracks optional parameters defined in JSON schemas but not yet exposed in MCP tool signatures.

## Status Summary

- ✅ **list_creative_formats**: Fixed - all parameters added (type, standard_only, category, format_ids)
- ✅ **get_products**: Fixed - filters and strategy_id parameters added
- ✅ **create_media_buy**: Fixed - reporting_webhook parameter added
- ✅ **list_authorized_properties**: Already complete - tags parameter implemented
- ⚠️ **list_creatives**: Needs 7 parameters
- ⚠️ **sync_creatives**: Needs 5 parameters

## list_creatives - Missing 7 Parameters

**Current signature:**
```python
def list_creatives(
    media_buy_id: str = None,
    buyer_ref: str = None,
    status: str = None,
    format: str = None,
    tags: list[str] = None,
    created_after: str = None,
    created_before: str = None,
    search: str = None,
    page: int = 1,
    limit: int = 50,
    sort_by: str = "created_date",
    sort_order: str = "desc",
    context: Context = None,
) -> ListCreativesResponse
```

**Missing parameters from JSON schema:**
1. **filters** (object) - Structured filters combining multiple criteria
   ```typescript
   {
     status?: string[];
     format_ids?: string[];
     tags?: string[];
     created_after?: string;
     created_before?: string;
   }
   ```

2. **sort** (object) - Sort configuration
   ```typescript
   {
     field: "created_date" | "updated_date" | "name" | "status";
     order: "asc" | "desc";
   }
   ```

3. **pagination** (object) - Pagination configuration
   ```typescript
   {
     page: number;
     limit: number;
   }
   ```

4. **include_assignments** (boolean) - Include creative-to-package assignments
5. **include_performance** (boolean) - Include performance metrics
6. **include_sub_assets** (boolean) - Include sub-assets for rich media
7. **fields** (array) - Field projection for partial responses

**Implementation notes:**
- Current tool has individual parameters (status, format, tags, etc.)
- Schema defines nested objects (filters, sort, pagination)
- Need to decide: keep flat parameters OR adopt nested objects
- Recommendation: Add nested objects as optional, support both patterns

**Breaking change risk:** LOW - All parameters are optional

## sync_creatives - Missing 5 Parameters

**Current signature:**
```python
def sync_creatives(
    creatives: list,
    media_buy_id: str = None,
    buyer_ref: str = None,
    assign_to_packages: list[str] = None,
    upsert: bool = True,
    context: Context = None,
) -> SyncCreativesResponse
```

**Missing parameters from JSON schema:**
1. **patch** (boolean) - Whether to patch existing creatives or replace
2. **assignments** (array) - Explicit creative-to-package assignments
   ```typescript
   {
     creative_id: string;
     package_id: string;
     weight?: number;
   }[]
   ```
3. **delete_missing** (boolean) - Delete creatives not in sync payload
4. **dry_run** (boolean) - Validate without making changes
5. **validation_mode** (enum) - Validation strictness level
   - "strict": Reject on any validation error
   - "warn": Log warnings but continue
   - "skip": No validation

**Implementation notes:**
- Most parameters affect sync behavior/semantics
- `dry_run` would be useful for validation
- `patch` vs replace affects idempotency
- `assignments` overlaps with `assign_to_packages`

**Breaking change risk:** LOW - All parameters are optional

## Recommendations

### Immediate (This PR)
- ✅ Add simple scalar parameters (filters to get_products, reporting_webhook to create_media_buy)
- ✅ Document remaining parameters for future work

### Next PR
- Add object-based parameters to list_creatives (filters, sort, pagination)
- Keep flat parameters for backward compatibility
- Implement both patterns in schema validation

### Future PRs
- Add sync_creatives parameters (patch, dry_run, validation_mode)
- Add fields projection support to list_creatives
- Consider auto-generation tooling to prevent future drift

## Testing Strategy

For each added parameter:
1. Add unit test for parameter acceptance
2. Add integration test for parameter behavior
3. Update contract tests if behavior changes
4. Document in API reference

## Related Issues

- https://github.com/scope3/adcp-sales-agent/issues/XXX - list_creatives missing filters
- https://github.com/scope3/adcp-sales-agent/issues/XXX - sync_creatives missing dry_run mode
