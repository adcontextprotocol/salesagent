# Test Agent Issue: `update_media_buy` Returns Empty `affected_packages`

**Date**: 2025-10-23
**Agent URL**: https://test-agent.adcontextprotocol.org
**Protocol**: A2A
**Endpoint**: `update_media_buy`

## Summary

The test agent's `update_media_buy` endpoint accepts requests and returns "success" but doesn't actually update media buys. The response contains an empty `affected_packages` array, indicating no packages were modified.

## Issue Details

### ❌ CRITICAL: `update_media_buy` Stub Implementation

**Status**: Test agent has non-functional stub implementation

**Problem**: The endpoint accepts creative assignment requests but doesn't persist changes or return proper update details.

**Evidence**:

1. **Request Sent Correctly** ✅
   ```json
   {
     "buyer_ref": "buy_PO-1761238937153",
     "packages": [
       {
         "buyer_package_ref": "pkg_default",
         "creative_ids": ["creative_1", "creative_2"]
       }
     ]
   }
   ```

2. **Response Claims Success** ✅
   ```json
   {
     "success": true,
     "message": "Media buy buy_PO-1761238937153 updated successfully.",
     "affected_packages": []  // ❌ EMPTY - should contain PackageUpdateResult[]
   }
   ```

3. **No Persistence** ❌
   - Calling `get_media_buy_delivery` after update shows no creatives assigned
   - Changes don't persist between requests
   - Cannot verify the update succeeded

### Expected Behavior (Per AdCP Spec)

According to the AdCP specification, `UpdateMediaBuyResponse.affected_packages` should contain:

```typescript
interface PackageUpdateResult {
  buyer_package_ref: string;
  changes_applied: {
    creative_ids?: {
      added: string[];
      removed: string[];
      current: string[];
    };
    // ... other change types
  };
}
```

**Example of correct response:**
```json
{
  "success": true,
  "message": "Media buy updated successfully.",
  "affected_packages": [
    {
      "buyer_package_ref": "pkg_default",
      "changes_applied": {
        "creative_ids": {
          "added": ["creative_1", "creative_2"],
          "removed": [],
          "current": ["creative_1", "creative_2"]
        }
      }
    }
  ]
}
```

### Impact

**Blocks Testing**:
- ❌ Cannot verify creative assignment workflows end-to-end
- ❌ Cannot test `update_media_buy` → `get_media_buy_delivery` integration
- ❌ Cannot validate that creative IDs persist correctly
- ❌ Misleading "success" responses hide that nothing actually happened

**Workarounds**:
- Use mock adapter for testing (local-only)
- Test individual components in isolation
- Wait for test agent fix before E2E creative assignment tests

## Verification Steps

To confirm the fix is deployed:

```bash
# 1. Create a media buy
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: YOUR_TOKEN' \
  -d '{
    "message": {
      "messageId": "test-create",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "create_media_buy",
          "input": {
            "promoted_offering": "Test Product",
            "product_ids": ["test_product"],
            "total_budget": 1000,
            "flight_start_date": "2025-11-01",
            "flight_end_date": "2025-11-30"
          }
        }
      }]
    }
  }'

# 2. Update with creative assignment
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: YOUR_TOKEN' \
  -d '{
    "message": {
      "messageId": "test-update",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "update_media_buy",
          "input": {
            "buyer_ref": "RETURNED_BUYER_REF_FROM_STEP_1",
            "packages": [{
              "buyer_package_ref": "pkg_default",
              "creative_ids": ["creative_1", "creative_2"]
            }]
          }
        }
      }]
    }
  }'

# Expected: affected_packages should contain PackageUpdateResult with changes_applied
# ✅ affected_packages[0].buyer_package_ref == "pkg_default"
# ✅ affected_packages[0].changes_applied.creative_ids.added == ["creative_1", "creative_2"]
# ✅ affected_packages[0].changes_applied.creative_ids.current == ["creative_1", "creative_2"]

# 3. Verify persistence with get_media_buy_delivery
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: YOUR_TOKEN' \
  -d '{
    "message": {
      "messageId": "test-delivery",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "get_media_buy_delivery",
          "input": {
            "buyer_refs": ["RETURNED_BUYER_REF_FROM_STEP_1"]
          }
        }
      }]
    }
  }'

# Expected: packages[0].creative_ids should contain ["creative_1", "creative_2"]
```

## Related Issues

- **2025-10-04**: Test agent `create_media_buy` authentication failure ([postmortem](./2025-10-04-test-agent-auth-bug.md))
- **2025-10-04**: Test agent `get_media_buy_delivery` parameter mismatch (expects `media_buy_id` instead of spec-compliant `media_buy_ids`)

## Recommendations

**For Test Agent Maintainers**:
1. Implement actual media buy update logic (persist changes)
2. Return proper `affected_packages` array with `PackageUpdateResult[]` objects
3. Include `changes_applied` details showing what changed
4. Ensure changes persist for subsequent `get_media_buy_delivery` calls

**For Sales Agent Developers**:
1. Continue using mock adapter for local creative assignment testing
2. Document test agent limitations in E2E test skips
3. Re-enable E2E creative assignment tests once test agent is fixed

## Contact

**Reporter**: Brian O'Kelley (via Little Rock V2 Investigation)
**Testing Framework**: AdCP Sales Agent E2E Tests
**Date Reported**: 2025-10-23
