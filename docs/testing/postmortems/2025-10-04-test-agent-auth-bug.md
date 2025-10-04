# Test Agent Issues - test-agent.adcontextprotocol.org

**Date**: 2025-10-04
**Agent URL**: https://test-agent.adcontextprotocol.org
**Protocol**: A2A
**Auth Token Used**: `L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8`

## Summary

The test agent at `test-agent.adcontextprotocol.org` has partial functionality but contains critical issues preventing full end-to-end testing of AdCP workflows.

## Issues Found

### 1. ❌ CRITICAL: `create_media_buy` Authentication Failure

**Status**: Blocking end-to-end testing

**Problem**: The `create_media_buy` endpoint rejects requests with "Missing or invalid x-adcp-auth header for authentication" even when the exact same authentication headers work successfully for other endpoints.

**Evidence**:
- ✅ `get_products` works with auth token `L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8`
- ❌ `create_media_buy` fails with same auth token and headers

**Request Example**:
```bash
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
  -H 'Authorization: Bearer L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
  -d '{
    "message": {
      "messageId": "test-123",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "create_media_buy",
          "input": {
            "promoted_offering": "Electric vehicles",
            "product_ids": ["connected_tv_premium"],
            "total_budget": 10000,
            "flight_start_date": "2025-10-10",
            "flight_end_date": "2025-10-31"
          }
        }
      }]
    }
  }'
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Failed to create media buy: Missing or invalid x-adcp-auth header for authentication."
  }
}
```

**Debug Log Confirmation**:
```json
{
  "type": "info",
  "message": "A2A: Custom fetch called for https://test-agent.adcontextprotocol.org/a2a",
  "headersBeingSet": ["Content-Type", "Accept", "x-adcp-auth", "Authorization"]
}
```

**Impact**: Cannot create media buys, which blocks testing of delivery reporting workflows.

**Recommendation**: Review auth validation logic specifically for `create_media_buy` endpoint. Either:
- Fix auth validation to match `get_products` behavior, OR
- Provide different auth token/scope for media buy creation

---

### 2. ⚠️ SPEC COMPLIANCE: `get_media_buy_delivery` Parameter Mismatch

**Status**: Non-compliant with AdCP spec

**Problem**: The `get_media_buy_delivery` endpoint expects parameter `media_buy_id` (singular) but the AdCP v1.6.0 specification defines `media_buy_ids` (plural array).

**AdCP Spec (v1.6.0)**:
```typescript
export interface GetMediaBuyDeliveryRequest {
  adcp_version?: string;
  media_buy_ids?: string[];  // PLURAL - array of IDs
  buyer_refs?: string[];
  status_filter?: ...;
  start_date?: string;
  end_date?: string;
}
```

**Test Agent Behavior**:
```bash
# Request with spec-compliant parameter name
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
  -d '{
    "message": {
      "messageId": "test-123",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "get_media_buy_delivery",
          "input": {
            "media_buy_ids": ["test-id"],
            "start_date": "2025-10-01",
            "end_date": "2025-10-31"
          }
        }
      }]
    }
  }'
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "artifacts": [{
      "parts": [{
        "data": {
          "success": false,
          "message": "Missing required parameter: 'media_buy_id'",
          "required_parameters": ["media_buy_id"],
          "received_parameters": ["media_buy_ids", "start_date", "end_date"]
        }
      }]
    }]
  }
}
```

**Impact**:
- Clients following AdCP spec will fail to use this endpoint
- Breaks interoperability with spec-compliant implementations
- May cause confusion for developers

**Recommendation**: Update endpoint to accept `media_buy_ids` (plural array) as specified in AdCP v1.6.0. For backward compatibility, you may optionally support both singular and plural forms.

---

## Working Endpoints ✅

### `get_products`
**Status**: ✅ Working correctly

**Test**:
```bash
curl -X POST https://test-agent.adcontextprotocol.org/a2a \
  -H 'Content-Type: application/json' \
  -H 'x-adcp-auth: L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
  -d '{
    "message": {
      "messageId": "test-123",
      "role": "user",
      "kind": "message",
      "parts": [{
        "kind": "data",
        "data": {
          "skill": "get_products",
          "input": {
            "promoted_offering": "Electric vehicles"
          }
        }
      }]
    }
  }'
```

**Response**: Returns 5 mock products with correct AdCP-compliant structure.

---

## Testing Checklist

To verify fixes:

- [ ] **Auth Fix**: `create_media_buy` should accept same auth headers as `get_products`
  ```bash
  # Should succeed with same auth token
  curl -X POST https://test-agent.adcontextprotocol.org/a2a \
    -H 'x-adcp-auth: L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
    -d '{"message":{"messageId":"test","role":"user","kind":"message","parts":[{"kind":"data","data":{"skill":"create_media_buy","input":{"promoted_offering":"test","product_ids":["connected_tv_premium"],"total_budget":10000,"flight_start_date":"2025-10-10","flight_end_date":"2025-10-31"}}}]}}'
  ```

- [ ] **Spec Compliance Fix**: `get_media_buy_delivery` should accept `media_buy_ids` (plural)
  ```bash
  # Should succeed with plural parameter name
  curl -X POST https://test-agent.adcontextprotocol.org/a2a \
    -H 'x-adcp-auth: L4UCklW_V_40eTdWuQYF6HD5GWeKkgV8U6xxK-jwNO8' \
    -d '{"message":{"messageId":"test","role":"user","kind":"message","parts":[{"kind":"data","data":{"skill":"get_media_buy_delivery","input":{"media_buy_ids":["mb-123"],"start_date":"2025-10-01","end_date":"2025-10-31"}}}]}}'
  ```

- [ ] **End-to-End Workflow**: Create media buy → Get delivery reports
  ```bash
  # 1. Create media buy (should return media_buy_id)
  # 2. Use returned ID to get delivery reports
  # 3. Verify delivery report structure matches AdCP spec
  ```

---

## Contact

**Reporter**: Brian O'Kelley (via AdCP Testing Framework)
**Testing Framework**: https://adcp-testing.fly.dev
**Date Reported**: 2025-10-04
