# Protocol Envelope Migration Plan

## Context

AdCP PR #113 removes protocol fields (status, message, task_id, context_id) from domain response schemas, moving them to a protocol envelope wrapper. This creates clean separation between business logic and protocol concerns.

## Current Architecture

```
CreateMediaBuyResponse (domain response)
├── status: "completed|working|submitted|..."  # Protocol field
├── task_id: str | None                        # Protocol field
├── buyer_ref: str                             # Domain field
├── media_buy_id: str                          # Domain field
├── packages: list[Package]                    # Domain field
└── errors: list[Error] | None                 # Domain field
```

## Target Architecture (Post PR #113)

```
Protocol Layer (MCP/A2A/REST)
└── ProtocolEnvelope
    ├── status: "completed|working|submitted|..."  # Protocol layer
    ├── task_id: str | None                        # Protocol layer
    ├── message: str                               # Protocol layer
    ├── context_id: str | None                     # Protocol layer
    ├── timestamp: datetime                        # Protocol layer
    └── payload: CreateMediaBuyResponse            # Domain response
        ├── buyer_ref: str                         # Domain field
        ├── media_buy_id: str                      # Domain field
        ├── packages: list[Package]                # Domain field
        └── errors: list[Error] | None             # Domain field
```

## Implementation Status

### ✅ Completed
1. Updated cached AdCP schemas (commit 19437523)
2. Created ProtocolEnvelope wrapper class (commit 30569d37)
3. 11 passing unit tests for protocol envelope

### 🔄 In Progress
4. Remove protocol fields from Pydantic response models

### ⏸️  Pending
5. Update all _impl functions to return domain-only responses
6. Add protocol envelope wrapping at transport boundaries
7. Update all tests (unit, integration, e2e)
8. Update documentation

## Migration Strategy

### Phase 1: Add Protocol Envelope Support (Non-Breaking)
- ✅ Create ProtocolEnvelope class
- ✅ Add tests for protocol envelope
- ⏸️  Keep protocol fields in domain responses (backward compatible)
- ⏸️  Optionally wrap responses in envelope at transport layer

### Phase 2: Deprecate Protocol Fields (Warning Phase)
- Add deprecation warnings when protocol fields are accessed
- Update documentation showing new pattern
- Provide migration guide for consumers

### Phase 3: Remove Protocol Fields (Breaking Change)
- Remove status, task_id, message, context_id from all response models
- Update all _impl functions to NOT set protocol fields
- Add protocol envelope wrapping at ALL transport boundaries:
  - MCP: Already has JSON-RPC envelope (tool response)
  - A2A: Already has Task/Artifact envelope
  - Testing: Use ProtocolEnvelope explicitly
- Update all tests to expect new structure

## Files Requiring Changes

### Response Models (src/core/schemas.py)
**Protocol fields to remove:**
- `CreateMediaBuyResponse`: status, task_id, adcp_version
- `UpdateMediaBuyResponse`: status, task_id, adcp_version
- `SyncCreativesResponse`: status, task_id, context_id, message, adcp_version
- `GetProductsResponse`: status, adcp_version
- `ListCreativeFormatsResponse`: status, adcp_version
- `ListCreativesResponse`: message, context_id, adcp_version
- `GetMediaBuyDeliveryResponse`: adcp_version
- `GetSignalsResponse`: status, adcp_version
- `ActivateSignalResponse`: status, message, adcp_version
- `ListAuthorizedPropertiesResponse`: status, adcp_version

**Keep in models (domain fields):**
- Business data (buyer_ref, media_buy_id, packages, errors, etc.)
- Workflow references (workflow_step_id - internal field)

### Implementation Functions (src/core/main.py)
**Update all _impl functions:**
- `_create_media_buy_impl`: Don't set `status`, return domain data only
- `_update_media_buy_impl`: Don't set `status`
- `_sync_creatives_impl`: Don't set `status`, `message`, `task_id`
- `_get_products_impl`: Don't set `status`
- `_list_creative_formats_impl`: Don't set `status`
- `_list_creatives_impl`: Don't set `message`, `context_id`
- `_get_media_buy_delivery_impl`: Remove any protocol field logic
- `_get_signals_impl`: Don't set `status`

**Add protocol metadata determination:**
- Helper function: `_determine_task_status(response) -> TaskStatus`
- Helper function: `_generate_response_message(response) -> str`
- These would be called at transport boundaries, not in _impl functions

### Transport Layer Wrapping

#### MCP Tools (src/core/main.py)
```python
# Current:
@mcp.tool()
def create_media_buy(...) -> CreateMediaBuyResponse:
    return _create_media_buy_impl(...)

# After Phase 3:
@mcp.tool()
def create_media_buy(...) -> dict:
    domain_response = _create_media_buy_impl(...)
    envelope = ProtocolEnvelope.wrap(
        payload=domain_response,
        status=_determine_task_status(domain_response),
        message=_generate_response_message(domain_response)
    )
    return envelope.model_dump()
```

**Issue**: FastMCP expects Pydantic models with type hints. Returning dict breaks type checking.
**Solution**: Create ProtocolEnvelopeResponse Pydantic model that FastMCP can serialize.

#### A2A Handlers (src/a2a_server/adcp_a2a_server.py)
```python
# Current:
response = core_create_media_buy_tool(...)
task.artifacts = [Artifact(data=response.model_dump())]

# After Phase 3:
domain_response = core_create_media_buy_tool(...)
envelope = ProtocolEnvelope.wrap(
    payload=domain_response,
    status=_determine_task_status(domain_response),
    task_id=task_id,
    context_id=context_id
)
task.artifacts = [Artifact(data=envelope.model_dump())]
```

### Tests Requiring Updates

#### Unit Tests
- `tests/unit/test_adcp_contract.py`: Update expected response structures
- `tests/unit/test_create_media_buy.py`: Don't expect status in response
- `tests/unit/test_sync_creatives.py`: Don't expect status, message
- All response model tests: Remove protocol field assertions

#### Integration Tests
- `tests/integration/test_mcp_*.py`: Expect envelope structure
- `tests/integration/test_a2a_*.py`: Expect envelope in artifact data
- `tests/integration/test_create_media_buy_roundtrip.py`: Update roundtrip logic

#### E2E Tests
- `tests/e2e/test_adcp_compliance.py`: Validate against new schemas
- Schema validation tests: Use updated schemas from PR #113

## Decision Points

### 🚨 CRITICAL: Should we do Phase 3 now?

**Arguments FOR removing protocol fields now:**
1. AdCP spec changed (PR #113 merged)
2. Clean architecture (separation of concerns)
3. Forward compatibility with spec
4. Already have ProtocolEnvelope implementation

**Arguments AGAINST removing protocol fields now:**
1. MASSIVE breaking change (~2000+ lines of code to update)
2. All tests will break (713 unit + 192 integration)
3. Need careful coordination of changes
4. Risk of introducing bugs during refactoring
5. Current implementation works and passes all tests

**Recommendation**: **DEFER Phase 3 to separate effort**

**Rationale**:
- Current code is functional and compliant with environment-based validation
- Protocol envelope infrastructure is in place (Phase 1 complete)
- Removing protocol fields is a massive refactor requiring dedicated sprint
- We can proceed with schema updates without breaking existing code
- ENVIRONMENT=production mode already handles extra fields gracefully

### Alternative: Hybrid Approach (RECOMMENDED)

Keep protocol fields in internal models, but:
1. ✅ Use updated schemas for validation (already done)
2. ✅ Have ProtocolEnvelope for explicit wrapping (already done)
3. ⏸️  Add `model_dump()` overrides to exclude protocol fields when needed
4. ⏸️  Document that protocol fields are for internal use only
5. ⏸️  Gradually migrate one endpoint at a time (controlled rollout)

## Next Steps (RECOMMENDED)

1. **Commit current work** (schema updates + ProtocolEnvelope)
2. **Document hybrid approach** (protocol fields internal, domain-only for external)
3. **Create issue** for Phase 3 migration (separate effort)
4. **Test current implementation** (verify environment-based validation works)
5. **Move forward** with other priorities (not blocked on this refactor)

## Related Files
- `src/core/protocol_envelope.py`: ProtocolEnvelope implementation
- `tests/unit/test_protocol_envelope.py`: Protocol envelope tests
- `tests/e2e/schemas/v1/_schemas_v1_core_protocol-envelope_json.json`: Official spec
- This document: `docs/protocol-envelope-migration.md`
