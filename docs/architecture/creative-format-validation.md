# Creative Format Validation Architecture

## Overview

As of PR #XXX (2025-11-18), format validation is now **consistent across all creative operations**:
- `sync_creatives` - Validates format exists before storing creative
- `create_media_buy` - Validates format when assigning creatives to packages
- `update_media_buy` - Validates format when modifying creative assignments

This document explains the validation architecture, caching strategy, and design decisions.

## Validation Flow

```
Creative Input (from buyer)
    ↓
1. Schema Validation (Pydantic)
    ↓
2. Format Existence Check
    ↓
   ┌─────────────────────┐
   │ In-Memory Cache     │ ← 1-hour TTL
   │ (registry._format_  │
   │  cache)             │
   └─────────────────────┘
    ↓ (if cache miss)
3. Fetch from Creative Agent
   (via ADCPMultiAgentClient)
    ↓
4. Store in Cache (1-hour TTL)
    ↓
5. Validate Format Exists
    ↓
   Success: Continue processing
   Failure: Return clear error
```

## Error Message Design

**Critical Requirement**: Error messages MUST distinguish between two failure scenarios:

### Scenario 1: Format Unknown (Agent Reachable)
```
Unknown format 'display_300x250_image' from agent https://creative.adcontextprotocol.org.
Format must be registered with the creative agent.
Use list_creative_formats to see available formats.
```

**Meaning**: The creative agent is online and responding, but the specified format doesn't exist.

**User Action**: Check format ID spelling, or call `list_creative_formats` to see available formats.

### Scenario 2: Agent Unreachable (Network Error)
```
Cannot validate format 'display_300x250_image': Creative agent at https://creative.adcontextprotocol.org
is unreachable or returned an error. Please verify the agent URL is correct and the agent is running.
Error: Connection refused
```

**Meaning**: The creative agent is offline, the URL is wrong, or there's a network issue.

**User Action**: Check agent URL, verify agent is running, check network connectivity.

## Caching Strategy

### Why In-Memory Cache?

**Rejected Alternative: File-Based Cache**
- ❌ Schema mismatch issues (library updates break cache)
- ❌ Git churn (cache file changes frequently)
- ❌ Stale data (12-day-old cache in production incident)
- ❌ Manual refresh required

**Chosen Solution: In-Memory Cache**
- ✅ Always fresh data (1-hour TTL)
- ✅ No schema mismatch (uses live library objects)
- ✅ No git churn
- ✅ Automatic refresh

### Cache Implementation

**Location**: `src/core/creative_agent_registry.py::CreativeAgentRegistry._format_cache`

**Structure**:
```python
self._format_cache: dict[str, CachedFormats] = {}

@dataclass
class CachedFormats:
    formats: list[Format]          # adcp library Format objects
    fetched_at: datetime
    ttl_seconds: int = 3600        # 1 hour default
```

**Cache Key**: `agent_url` (e.g., "https://creative.adcontextprotocol.org")

**Expiry Logic**:
```python
def is_expired(self) -> bool:
    return datetime.now(UTC) > self.fetched_at + timedelta(seconds=self.ttl_seconds)
```

### Cache Hit Rate Optimization

**Within Single Request**: Multiple creatives with same format → 1 agent call
```python
sync_creatives([
    {"format_id": "display_300x250", ...},  # Cache miss → fetch from agent
    {"format_id": "display_300x250", ...},  # Cache hit ✓
    {"format_id": "display_300x250", ...},  # Cache hit ✓
])
```

**Across Requests** (within 1 hour): Format specs cached per agent
```python
# Request 1 (12:00 PM)
sync_creatives([{"format_id": "display_300x250", ...}])  # Fetch + cache

# Request 2 (12:15 PM)
sync_creatives([{"format_id": "display_300x250", ...}])  # Cache hit ✓

# Request 3 (1:05 PM)
sync_creatives([{"format_id": "display_300x250", ...}])  # Cache expired, re-fetch
```

### Cache Tradeoffs

**Benefits**:
1. **Performance**: Eliminates redundant HTTP calls to creative agent
2. **Resilience**: Agent downtime doesn't block operations for cached formats
3. **Consistency**: All operations use same cache (MCP, A2A, Admin UI)

**Tradeoffs**:
1. **Staleness Window**: Format spec changes take up to 1 hour to propagate
   - Mitigation: 1-hour TTL is acceptable for format specs (rarely change)
2. **Memory Usage**: Cache grows with number of unique creative agents
   - Mitigation: Bounded by number of agents × formats per agent (typically < 100 formats)
3. **No Persistence**: Cache lost on server restart
   - Mitigation: Acceptable - cache rebuilds on first request after restart

## Optimization Considerations

### Current Behavior: Validate All Operations

**Rationale for Always Validating**:
1. **Format Spec Changes**: Creative agent may update format requirements (new required assets, dimension changes)
2. **Agent Migration**: Creative agent URL may change or format may move to different agent
3. **Consistency**: Same validation logic for create and update operations
4. **Security**: Prevents stale/invalid formats from being used in new campaigns

### Potential Future Optimization: Skip Validation on Unchanged Updates

**Scenario**: Creative update without format change
```python
# Existing creative: format = "display_300x250_image"
sync_creatives([{
    "creative_id": "existing_123",
    "name": "Updated Name",  # Only name changed
    "format_id": "display_300x250_image"  # Same format
}])
```

**Optimization**: Skip format validation if:
- Creative already exists in database
- `format_id` hasn't changed
- Not in `patch=False` (full upsert) mode

**Code Sketch**:
```python
if existing_creative and existing_creative.format == format_id:
    # Format unchanged, skip validation
    logger.debug(f"Skipping format validation for {creative_id} (format unchanged)")
    format_spec = None  # Don't need spec for update
else:
    # New creative or format changed, validate
    format_spec = loop.run_until_complete(registry.get_format(agent_url, format_id))
```

**Concerns**:
1. **Format Spec Drift**: Agent may update format requirements without changing format ID
2. **Edge Case Complexity**: Adds conditional logic that may hide bugs
3. **Marginal Benefit**: Cache already makes validation fast (< 10ms for cache hit)
4. **Breaking Changes**: If agent deprecates a format, updates should fail too

**Recommendation**: **Do NOT implement this optimization**. The cost/benefit doesn't justify the added complexity and edge case risks. Cache already makes validation negligible.

## Implementation Details

### Async/Sync Bridge Pattern

**Location**: `src/core/tools/creatives.py` lines 192-235

**Pattern** (matches `media_buy_create.py`):
```python
import asyncio

# Create new event loop for this sync context
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    format_spec = loop.run_until_complete(registry.get_format(agent_url, format_id))
finally:
    loop.close()
```

**Why This Pattern**:
- ✅ Explicit event loop management (no hidden global state)
- ✅ Proper cleanup (always closes loop)
- ✅ Consistent with `media_buy_create.py`
- ✅ Avoids `run_async_in_sync_context()` helper (clearer, fewer abstractions)

**Rejected Alternative**: `run_async_in_sync_context()`
- ❌ Implicit event loop management
- ❌ Potential for event loop conflicts
- ❌ Less explicit about what's happening

## Testing Strategy

### Test Coverage

**Location**: `tests/unit/test_sync_creatives_format_validation.py`

**Scenarios Tested**:
1. ✅ Format validation success (format exists)
2. ✅ Format unknown (agent reachable, format doesn't exist)
3. ✅ Agent unreachable (network error, connection refused)
4. ✅ String format_id auto-upgrade (legacy compatibility)
5. ✅ Multiple creatives (partial success/failure)
6. ✅ Format validation caching (no duplicate agent calls)
7. ✅ Missing format_id (validation error)
8. ✅ Error message clarity (unknown vs unreachable)
9. ✅ Update with unchanged format (still validates)

### Test Philosophy

**Unit Tests**: Mock creative agent registry, test validation logic
- Focus: Error handling, message clarity, edge cases

**Integration Tests** (future): Real PostgreSQL, mock creative agent HTTP
- Focus: Database transaction isolation, rollback on validation failure

**E2E Tests** (existing): Real creative agent, real database
- Focus: End-to-end validation flow with actual AdCP protocol

## Related Documentation

- **Creative Model Architecture**: `docs/architecture/creative-model-architecture.md`
  - Explains hybrid model (AdCP spec + internal fields)
  - Documents `model_dump()` serialization pattern

- **Format Spec Cache Refactor**: GitHub Issue #767 (future)
  - Proposes `validate_creative` endpoint for full manifest validation
  - Current: Only checks format exists
  - Future: Validate creative manifest matches format requirements

- **AdCP Protocol Compliance**: `docs/testing/adcp-compliance.md`
  - Testing patterns for AdCP spec compliance
  - Contract tests for all request/response schemas

## Incident Postmortem Reference

**Original Issue**: sync_creatives succeeded, create_media_buy failed with "unknown format"

**Root Cause**:
- `sync_creatives` had NO format validation (just stored creative)
- `create_media_buy` had FULL format validation (fetched from agent)
- Different code paths led to inconsistent behavior

**Resolution**:
- Added format validation to `sync_creatives` (this document)
- Removed file-based cache (schema mismatch issues)
- Unified validation logic across all operations

**Date**: 2025-11-18

**Lessons Learned**:
1. Always validate at the point of entry (sync_creatives), not later (create_media_buy)
2. In-memory caching is simpler and more reliable than file-based caching
3. Consistent validation across all operations prevents surprises
4. Clear error messages distinguish infrastructure vs application errors

## Future Work

### 1. Full Manifest Validation (GitHub #767)

**Current**: Only validates format exists
**Future**: Validate creative manifest matches format requirements

**API**: `validate_creative` endpoint on creative agent
```python
response = await registry.validate_creative(
    agent_url=agent_url,
    format_id=format_id,
    creative_manifest={
        "creative_id": "creative_123",
        "name": "Banner",
        "format_id": "display_300x250_image",
        "assets": {...}
    }
)

if not response.is_valid:
    raise ValueError(f"Creative validation failed: {response.errors}")
```

### 2. Format Spec Versioning

**Challenge**: Format specs may evolve (new required assets, dimension changes)
**Solution**: Version format specs, validate against specific version

**Example**:
```python
format_id = {
    "agent_url": "https://creative.adcontextprotocol.org",
    "id": "display_300x250_image",
    "version": "2.0"  # Optional version pin
}
```

### 3. Batch Format Validation

**Optimization**: Validate all formats in single agent call
**API**: `validate_formats` endpoint (batch operation)

**Example**:
```python
# Instead of N calls for N formats
for creative in creatives:
    format_spec = await registry.get_format(agent_url, format_id)

# Single call for all unique formats
unique_formats = set(c.format_id for c in creatives)
format_specs = await registry.get_formats(agent_url, list(unique_formats))
```

**Benefit**: Reduces HTTP overhead for bulk creative sync operations

## Summary

**Key Takeaways**:
1. Format validation is now **consistent** across all creative operations
2. **In-memory cache** (1-hour TTL) provides performance + freshness
3. **Clear error messages** distinguish "format unknown" vs "agent unreachable"
4. **No optimization needed** for existing creative updates (cache already fast)
5. **Explicit event loop** pattern ensures safe async/sync bridging

**When in Doubt**:
- Always validate formats (don't skip for optimization)
- Always use in-memory cache (don't add file-based caching)
- Always provide clear error messages (distinguish network vs application errors)
