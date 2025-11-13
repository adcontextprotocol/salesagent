# Fix: Media Buy Approval Error Handling

## Problem

When trying to approve a media buy in the admin UI at `/admin/tenant/{id}/media-buy/{media_buy_id}/approve`, the system would crash with the error:

```
Media buy approved but adapter creation failed: Adapter creation failed:
'CreateMediaBuyError' object has no attribute 'media_buy_id'
```

## Root Cause

The `execute_approved_media_buy()` function in `src/core/tools/media_buy_create.py` was calling the adapter's `create_media_buy()` method, which returns a `CreateMediaBuyResponse`. This is a union type that can be either:

1. `CreateMediaBuySuccess` (has `media_buy_id` attribute)
2. `CreateMediaBuyError` (has `errors` attribute, but NO `media_buy_id`)

The code was assuming the response was always successful and directly accessing `response.media_buy_id` without checking the response type. When the adapter returned an error response, accessing the non-existent `media_buy_id` attribute caused an `AttributeError`.

## Solution

Added a type check after calling `_execute_adapter_media_buy_creation()` to detect error responses before attempting to access `response.media_buy_id`:

```python
# Check if adapter returned an error response
if isinstance(response, CreateMediaBuyError):
    # Adapter returned error response (not an exception)
    error_messages = [str(err) for err in response.errors] if response.errors else ["Unknown error"]
    error_msg = "; ".join(error_messages)
    logger.error(f"[APPROVAL] Adapter creation failed for {media_buy_id}: {error_msg}")
    return False, error_msg
```

This fix:
- ✅ Properly detects error responses from the adapter
- ✅ Extracts meaningful error messages from the `errors` array
- ✅ Returns a proper error message to the approval route
- ✅ Prevents the `AttributeError` by checking type before accessing `media_buy_id`

## Files Changed

1. `src/core/tools/media_buy_create.py` - Added error response check in `execute_approved_media_buy()`
2. `tests/unit/test_approval_error_handling.py` - Added unit tests documenting the schema structure

## Testing

Created unit tests that verify:
- `CreateMediaBuyError` has `errors` field but not `media_buy_id`
- `CreateMediaBuySuccess` has `media_buy_id` field
- `isinstance()` check correctly distinguishes error from success responses
- Error string representation works correctly

## Impact

This fix resolves the approval crash and provides better error messages to users when adapter creation fails during manual approval. The error messages now properly surface the underlying adapter issues (e.g., "Budget exceeds daily limit", "Requested inventory not available") instead of crashing with an `AttributeError`.
