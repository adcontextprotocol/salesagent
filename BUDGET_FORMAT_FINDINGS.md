# AdCP Budget Format Analysis - CORRECTED

## Executive Summary

**YOU WERE RIGHT!** The AdCP specification uses **plain numbers for ALL budget fields**. Currency is always determined by the `pricing_option_id` selection, never specified in the budget field itself.

Our cached schemas were outdated and incorrectly referenced a `budget.json` schema that doesn't exist in the official AdCP spec.

## ✅ ACTUAL AdCP Spec (Official)

**ALL budgets are plain numbers everywhere:**

### 1. Top-Level Budget (CreateMediaBuyRequest)
```json
{
  "budget": 5000.0  // Plain number
}
```
- **Type**: `number`
- **Required**: Yes
- **Description**: "Total budget for this media buy"
- **Currency**: Determined by `pricing_option_id` in packages
- **Source**: https://adcontextprotocol.org/schemas/v1/media-buy/create-media-buy-request.json

### 2. Package-Level Budget (PackageRequest)
```json
{
  "budget": 2500.0  // Plain number
}
```
- **Type**: `number` (minimum: 0)
- **Required**: Yes (part of anyOf requirement)
- **Description**: "Budget allocation for this package in the media buy's currency"
- **Currency**: Determined by selected `pricing_option_id`
- **Source**: https://adcontextprotocol.org/schemas/v1/media-buy/package-request.json

### 3. Package Budget (Response)
```json
{
  "budget": 2500.0  // Plain number
}
```
- **Type**: `number`
- **Currency**: Comes from associated pricing option
- **Source**: https://adcontextprotocol.org/schemas/v1/core/package.json

### 4. MediaBuy.total_budget (Response)
```json
{
  "total_budget": 5000.0  // Plain number
}
```
- **Type**: `number`
- **Source**: https://adcontextprotocol.org/schemas/v1/core/media-buy.json

## ❌ INCORRECT: Our Cached Schemas

### Problem: Outdated Schema Files

Our cached file `tests/e2e/schemas/v1/_schemas_v1_media-buy_package-request_json.json` incorrectly references:

```json
"budget": {
  "$ref": "/schemas/v1/core/budget.json"  // ❌ This schema doesn't exist!
}
```

**Facts:**
- ✅ Official AdCP spec has **NO `budget.json` schema** (verified via https://adcontextprotocol.org/schemas/v1/index.json)
- ✅ All budgets in official spec are **plain numbers**
- ❌ Our cached schemas reference a non-existent `budget.json` (object format)
- ❌ Schema download script pulled outdated or incorrect schemas

## Current Implementation Status

### ✅ E2E Test Helper (tests/e2e/adcp_request_builder.py)
**NOW FIXED**:

```python
# Line 82 - CORRECTED
"budget": total_budget,  # Top-level budget is plain number per AdCP spec

# Line 77 - NEEDS FIXING
"budget": {"total": total_budget, "currency": currency, "pacing": pacing},  # ❌ WRONG!
# Should be:
"budget": total_budget,  # Package budget is also plain number per spec
```

### ⚠️ Python Schemas (src/core/schemas.py)
**TOO FLEXIBLE** - Accepts both formats, should only accept number:

```python
# Current (accepts both object and number)
budget: Budget | float | None = Field(...)

# Should be (plain number only per spec)
budget: float | None = Field(...)
```

### ✅ Test Agent Behavior
The test agent correctly implements the AdCP spec:
- ✅ Expects ALL budgets as plain numbers
- ✅ Rejects object format (which is correct!)
- ❌ Our E2E tests were sending wrong object format

## Required Fixes

### 1. ✅ Fix top-level budget (DONE)
Line 82 in `adcp_request_builder.py` - already fixed to use plain number

### 2. ❌ Fix package-level budget (TODO)
Line 77 in `adcp_request_builder.py`:
```python
# Change from:
"budget": {"total": total_budget, "currency": currency, "pacing": pacing},

# To:
"budget": total_budget,
```

### 3. Update cached schemas (TODO)
Re-download schemas to get correct versions without `budget.json` references:
```bash
./scripts/schema/download-schemas.sh
```

### 4. Update Python schemas (TODO)
Enforce spec-compliant types:
```python
class CreateMediaBuyRequest(BaseModel):
    budget: float = Field(...)  # Plain number per spec

class Package(BaseModel):
    budget: float | None = Field(None)  # Plain number per spec
```

### 5. Remove Budget object class (TODO)
Since budgets are always plain numbers, we don't need a `Budget` class for AdCP fields.
Keep `Budget` class only if used internally for non-AdCP purposes.

## Currency Resolution (AdCP Spec)

**Simple rule**: Currency ALWAYS comes from `pricing_option_id`, never from budget field.

### In Requests
- Select a `pricing_option_id` that specifies the currency
- Provide budget as plain number in that currency
- No currency field in budget itself

### In Responses
- Budget is plain number
- Currency determined by associated pricing option
- No currency field in budget field

## Conclusion

**The test agent was 100% correct.** Our implementation was wrong in two places:

1. ❌ **E2E test helper** was sending object format `{total, currency, pacing}` for package budgets
2. ❌ **Cached schemas** incorrectly referenced non-existent `budget.json`
3. ⚠️ **Python schemas** too flexible (should enforce plain number only)

**The fix**: Use plain numbers for ALL budget fields, everywhere. Currency is implicit from `pricing_option_id`.

## Verification

Confirmed via official AdCP spec:
- ✅ https://adcontextprotocol.org/schemas/v1/index.json - No `budget.json` listed
- ✅ https://adcontextprotocol.org/schemas/v1/media-buy/package-request.json - budget is `number`
- ✅ https://adcontextprotocol.org/schemas/v1/media-buy/create-media-buy-request.json - budget is `number`
