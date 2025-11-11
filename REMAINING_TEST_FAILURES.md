# Remaining Test Failures - adcp v1.2.1 Migration

**Status**: 1382/1415 tests passing (97.7%), 33 failures remaining

## Summary by Category

### 1. A2A Parameter Tests (4 failures)
**Files**: `tests/unit/test_a2a_parameter_mapping.py`

**Issue**: Tests expect package data without `status` field, but Pydantic now requires it.

**Failures**:
- `test_update_media_buy_uses_packages_parameter` - Package now includes status field
- `test_update_media_buy_backward_compatibility_with_updates` - KeyError: 'updates'
- `test_update_media_buy_validates_required_parameters` - ServerError from validation
- `test_create_media_buy_validates_required_adcp_parameters` - Error message format changed

**Fix**: Update test expectations to match Pydantic validation behavior.

### 2. Adapter Package Tests (5 failures)
**Files**: `tests/unit/test_adapter_packages_fix.py`, `tests/unit/test_gam_workflow_packages.py`

**Issue**: Tests expect `platform_line_item_id` field on Package objects, but this isn't part of AdCP spec.

**Failures**:
- Kevel: `test_kevel_live_mode_returns_packages_with_flight_ids`
- Triton: `test_triton_live_mode_returns_packages_with_flight_ids`
- Xandr: `test_xandr_returns_packages_with_package_ids_and_line_item_ids`
- GAM: `test_activation_workflow_returns_packages_with_line_item_ids`
- GAM: `test_success_path_returns_packages_with_line_item_ids`

**Options**:
1. Store platform_line_item_id in database only (not in Package response)
2. Add as internal field in wrapper class (like workflow_step_id)
3. Update tests to not expect this field (simplest - it's internal tracking)

**Recommendation**: Option 3 - Remove platform_line_item_id expectations from tests. This is internal tracking data that shouldn't be in AdCP-compliant responses.

### 3. Schema Compliance Test (1 failure)
**File**: `tests/unit/test_adapter_schema_compliance.py`

**Issue**: Pre-existing - ActivateSignalResponse schema test expects old pattern.

**Failure**:
- `test_response_adapter_matches_spec[ActivateSignalResponse-ActivateSignalResponse]`

**Fix**: Update test to handle oneOf pattern (ActivateSignalSuccess | ActivateSignalError).

### 4. Inline Creative Tests (1 failure)
**File**: `tests/unit/test_inline_creatives_in_adapters.py`

**Issue**: Test expects creative_ids to be accessible as list attribute.

**Failure**:
- `test_mock_adapter_includes_creative_ids`

**Fix**: Update test to handle Package Pydantic object properly.

### 5. A2A Response Tests (4 failures)
**File**: `tests/integration/test_a2a_response_message_fields.py`

**Issue**: Tests expect `message` field on response objects, but oneOf pattern changes structure.

**Failures**:
- `test_sync_creatives_message_field_exists`
- `test_get_products_message_field_exists`
- `test_create_media_buy_response_to_dict`
- `test_all_response_types_have_str_or_message`

**Fix**: Update tests to handle oneOf Success/Error discriminator pattern.

### 6. GAM Lifecycle Tests (2 failures)
**File**: `tests/integration/test_gam_lifecycle.py`

**Issue**: Tests may expect specific error structure or Package fields.

**Failures**:
- `test_lifecycle_workflow_validation`
- `test_activation_validation_with_guaranteed_items`

**Fix**: Update to handle oneOf pattern and Pydantic Package objects.

### 7. GAM Pricing Tests (2 failures)
**File**: `tests/integration/test_gam_pricing_restriction.py`

**Failures**:
- `test_gam_accepts_cpm_pricing_model`
- `test_gam_accepts_cpm_from_multi_pricing_product`

**Fix**: Similar to pricing integration tests - check for oneOf pattern handling.

### 8. MCP Connection Tests (3 failures)
**File**: `tests/integration/test_mcp_client_util.py`

**Issue**: MCP server connection tests (expected - servers not running).

**Failures**:
- `test_connect_to_audience_agent`
- `test_connect_to_local_mcp_server`
- `test_respects_user_url_exactly`

**Fix**: Expected failures - these require actual MCP servers running.

### 9. MCP Roundtrip Test (1 failure)
**File**: `tests/integration/test_mcp_tool_roundtrip_minimal.py`

**Failure**:
- `test_update_media_buy_minimal`

**Fix**: Update to handle oneOf pattern and Package Pydantic validation.

### 10. Spec Compliance Tests (2 failures)
**File**: `tests/integration/test_spec_compliance.py`

**Failures**:
- `test_spec_compliance_tools_exposed`
- `test_core_adcp_tools_callable`

**Fix**: May need import updates for adcp library types.

### 11. Tenant Settings Test (1 failure)
**File**: `tests/integration/test_tenant_settings_comprehensive.py`

**Failure**:
- `test_settings_page`

**Fix**: May be unrelated to migration - check specific error.

### 12. Unified Delivery Tests (6 failures)
**File**: `tests/integration/test_unified_delivery.py`

**Issue**: Delivery endpoint tests may expect old Package structure.

**Failures**:
- `test_unified_delivery_single_buy`
- `test_unified_delivery_multiple_buys`
- `test_unified_delivery_active_filter`
- `test_unified_delivery_all_filter`
- `test_unified_delivery_completed_filter`
- `test_deprecated_endpoint_backward_compatibility`

**Fix**: Update to handle Pydantic Package objects in delivery responses.

### 13. Workflow Test (1 failure)
**File**: `tests/integration/test_workflow_with_server.py`

**Failure**:
- `test_workflow_with_manual_approval`

**Fix**: Update to handle oneOf pattern in workflow responses.

## Priority Order

1. **High**: A2A parameter tests (4) - Core protocol functionality
2. **High**: Adapter package tests (5) - Core adapter functionality
3. **Medium**: A2A response tests (4) - Protocol response structure
4. **Medium**: Unified delivery tests (6) - Core delivery functionality
5. **Medium**: GAM lifecycle/pricing tests (4) - Adapter-specific
6. **Low**: MCP connection tests (3) - Expected failures (servers not running)
7. **Low**: Schema compliance test (1) - Pre-existing issue
8. **Low**: Other integration tests (6) - Various issues

## Next Steps

1. Fix A2A parameter mapping tests (update expectations for status field)
2. Fix adapter package tests (remove platform_line_item_id expectations)
3. Fix A2A response tests (handle oneOf pattern)
4. Fix unified delivery tests (handle Pydantic Package objects)
5. Fix remaining integration tests
6. Document any tests that are expected to fail (MCP connection without servers)
