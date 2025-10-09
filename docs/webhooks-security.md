# AdCP Webhook Security and Reliability

This document describes the enhanced webhook delivery implementation based on AdCP webhook specification PR #86.

## Security Features

### HMAC-SHA256 Signature Verification

All webhooks include cryptographic signatures to verify authenticity:

**Headers:**
- `X-ADCP-Signature`: HMAC-SHA256 signature (hex)
- `X-ADCP-Timestamp`: ISO 8601 timestamp (UTC)

**Signature Format:**
```
signature = HMAC-SHA256(webhook_secret, timestamp + "." + json_payload)
```

**Minimum Requirements:**
- Webhook secrets must be at least 32 characters
- Constant-time comparison prevents timing attacks
- Signatures use sorted, compact JSON (`separators=(",", ":")`)

### Replay Attack Prevention

Webhooks include timestamps and receivers should validate:
- Timestamp is recent (within 5-minute window by default)
- Timestamp is not in the future
- Each webhook is only processed once

## Reliability Features

### Circuit Breaker Pattern

Per-endpoint circuit breakers prevent cascading failures:

**States:**
- `CLOSED`: Normal operation
- `OPEN`: Endpoint failing, requests rejected
- `HALF_OPEN`: Testing recovery after timeout

**Thresholds:**
- Opens after 5 consecutive failures
- Timeout: 60 seconds before retry
- Closes after 2 successful deliveries in HALF_OPEN state

### Exponential Backoff with Jitter

Retry logic uses exponential backoff to prevent thundering herd:

```
delay = (base_delay * 2^attempt) + random(0, 1)
```

**Configuration:**
- Base delay: 1 second
- Max retries: 3
- Jitter: 0-1 seconds random

### Bounded Queues

Each endpoint has a bounded queue to prevent memory exhaustion:
- Maximum: 1000 webhooks per endpoint
- Dropped webhooks are logged
- Isolation prevents one slow endpoint affecting others

## Enhanced Payload Fields

### New Fields

**`is_adjusted`** (boolean):
- Indicates late-arriving data that replaces previous reports
- Used when historical data is corrected
- Recipients should update their records for the reporting period

**`notification_type`** (string):
- `"scheduled"`: Regular periodic update
- `"final"`: Final report for completed campaign
- `"adjusted"`: Late-arriving data (when `is_adjusted=true`)

## Configuration

### Database Schema

The `push_notification_configs` table includes:

```sql
webhook_secret VARCHAR(500) NULL  -- HMAC-SHA256 secret (min 32 chars)
```

### Setting Up Webhooks

**Publisher Configuration:**

```python
from src.services.webhook_delivery_service_v2 import enhanced_webhook_delivery_service

# Send webhook with security features
enhanced_webhook_delivery_service.send_delivery_webhook(
    media_buy_id="buy_123",
    tenant_id="tenant_1",
    principal_id="buyer_1",
    reporting_period_start=datetime(2025, 10, 1, tzinfo=UTC),
    reporting_period_end=datetime(2025, 10, 2, tzinfo=UTC),
    impressions=100000,
    spend=500.00,
    is_adjusted=False,  # Set to True for late-arriving data
)
```

**Buyer Verification:**

```python
from src.services.webhook_verification import verify_adcp_webhook, WebhookVerificationError

@app.post("/webhooks/adcp")
def receive_webhook(request):
    try:
        # Verify webhook signature and timestamp
        verify_adcp_webhook(
            webhook_secret="your-secret-at-least-32-characters-long",
            payload=request.json(),
            request_headers=dict(request.headers)
        )

        # Process verified webhook
        process_delivery_data(request.json())
        return {"status": "success"}

    except WebhookVerificationError as e:
        logger.warning(f"Invalid webhook: {e}")
        return {"error": str(e)}, 401
```

## Monitoring

### Circuit Breaker State

Check circuit breaker status for an endpoint:

```python
state, failures = enhanced_webhook_delivery_service.get_circuit_breaker_state(
    "https://buyer.example.com/webhooks"
)
# state: CircuitState.CLOSED, OPEN, or HALF_OPEN
# failures: consecutive failure count
```

### Manual Recovery

Reset a circuit breaker manually:

```python
enhanced_webhook_delivery_service.reset_circuit_breaker(
    "https://buyer.example.com/webhooks"
)
```

### Queue Status

Queue metrics are logged at shutdown:
- Active media buys
- Open circuit breakers
- Non-empty queues with sizes

## Security Best Practices

### For Publishers (Sending Webhooks)

1. **Strong Secrets**: Use cryptographically random secrets (32+ chars)
2. **Rotation**: Rotate webhook secrets periodically
3. **HTTPS Only**: Always use HTTPS endpoints
4. **Monitoring**: Track circuit breaker states and failed deliveries
5. **Rate Limiting**: Bounded queues prevent resource exhaustion

### For Buyers (Receiving Webhooks)

1. **Verify Signatures**: Always validate `X-ADCP-Signature` header
2. **Check Timestamps**: Reject webhooks outside 5-minute window
3. **Prevent Replays**: Track processed webhook IDs or timestamps
4. **Use Constant-Time Comparison**: Prevent timing attacks
5. **HTTPS Only**: Expose webhook endpoints over HTTPS only

## Migration from Legacy Webhook Service

### Differences from `webhook_delivery_service.py`

**New Features:**
- HMAC-SHA256 signatures
- Circuit breaker pattern
- Bounded queues
- `is_adjusted` flag
- Exponential backoff with jitter

**Backwards Compatibility:**
- Same method signature (added optional parameters)
- Can run both services simultaneously during migration
- Database schema extends (doesn't break) existing tables

### Migration Steps

1. **Add webhook secrets** to `push_notification_configs`
2. **Update calling code** to use `enhanced_webhook_delivery_service`
3. **Configure receivers** to verify signatures
4. **Monitor circuit breakers** in production
5. **Remove legacy service** after validation

## Testing

### Unit Tests

```python
from src.services.webhook_verification import WebhookVerifier, WebhookVerificationError

def test_webhook_verification():
    verifier = WebhookVerifier(
        webhook_secret="test-secret-at-least-32-characters-long",
        replay_window_seconds=300
    )

    # Test valid webhook
    payload = {"test": "data"}
    timestamp = datetime.now(UTC).isoformat()
    signature = verifier._generate_signature(payload, timestamp)

    assert verifier.verify_webhook(payload, signature, timestamp)

    # Test replay attack
    old_timestamp = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    try:
        verifier.verify_webhook(payload, signature, old_timestamp)
        assert False, "Should have raised"
    except WebhookVerificationError:
        pass
```

### Integration Tests

See `tests/integration/test_webhook_security.py` for comprehensive tests.

## Performance Considerations

### Circuit Breakers

- **Memory**: O(n) where n = number of unique endpoints
- **Thread-safe**: All operations use locks
- **Overhead**: Minimal (< 1ms per webhook)

### Queues

- **Memory**: Max 1000 webhooks × payload size per endpoint
- **Bounded**: Drops oldest webhooks when full
- **Per-endpoint**: Isolation prevents cascading issues

### HMAC Generation

- **Cost**: ~0.1ms per webhook (negligible)
- **No Network**: Computed locally
- **Deterministic**: Same input always produces same signature

## References

- [AdCP Webhook Specification PR #86](https://github.com/adcontextprotocol/adcp/pull/86)
- [HMAC-SHA256 RFC 2104](https://tools.ietf.org/html/rfc2104)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Exponential Backoff](https://en.wikipedia.org/wiki/Exponential_backoff)
