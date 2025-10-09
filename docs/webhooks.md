# Webhook Integration Guide

## Overview

Webhooks allow you to receive real-time notifications when events occur in your ad campaigns (creative approvals, media buy status changes, etc.). This guide explains how to register and securely verify webhooks.

## Quick Start

1. **Register a webhook** in the Admin UI under Principal → Webhooks
2. **Choose HMAC-SHA256 authentication** (recommended for production)
3. **Implement verification** in your webhook endpoint (examples below)
4. **Test the integration** with a sample webhook

## Security

### SSRF Protection

All webhook URLs are validated to prevent Server-Side Request Forgery attacks:

- ✅ Public HTTPS/HTTP endpoints
- ❌ Private networks (10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12)
- ❌ Localhost / loopback addresses
- ❌ Link-local addresses (169.254.0.0/16 - AWS metadata service)
- ❌ Cloud metadata services

### HMAC-SHA256 Authentication

Webhooks are signed with HMAC-SHA256 to ensure authenticity:

- **Signature Header**: `X-Webhook-Signature: sha256=<hex_digest>`
- **Timestamp Header**: `X-Webhook-Timestamp: <unix_timestamp>`
- **Replay Protection**: Timestamps older than 5 minutes are rejected

## Webhook Payload Format

All webhooks send JSON payloads with this structure:

```json
{
  "step_id": "step_abc123",
  "object_type": "creative",
  "object_id": "creative_xyz789",
  "action": "approval_required",
  "status": "completed",
  "step_type": "creative_approval",
  "owner": "publisher",
  "timestamp": "2025-10-04T14:30:00Z"
}
```

### Field Descriptions

- `step_id`: Unique workflow step identifier
- `object_type`: Type of object (creative, media_buy, etc.)
- `object_id`: ID of the object
- `action`: What action was taken/required
- `status`: Current status (pending, completed, failed, requires_approval)
- `step_type`: Type of workflow step
- `owner`: Who needs to act (principal, publisher, system)
- `timestamp`: ISO 8601 timestamp of the event

### Common Event Types

| Event Type | Description |
|------------|-------------|
| `creative_approval` | Creative requires manual review |
| `media_buy_status` | Media buy status changed (active, paused, completed) |
| `workflow_status_update` | Any workflow step status change |

## Implementation Examples

### Python (Flask)

```python
import hmac
import hashlib
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# Store this securely (environment variable, secrets manager)
WEBHOOK_SECRET = "your_hmac_secret_from_admin_ui"

@app.route("/webhooks/adcp", methods=["POST"])
def handle_adcp_webhook():
    """Handle incoming AdCP webhooks with HMAC verification."""

    # 1. Get signature and timestamp from headers
    signature = request.headers.get("X-Webhook-Signature", "")
    timestamp = request.headers.get("X-Webhook-Timestamp")

    if not signature or not timestamp:
        return jsonify({"error": "Missing signature headers"}), 401

    # 2. Replay attack prevention (5 minute window)
    try:
        webhook_time = int(timestamp)
        if abs(time.time() - webhook_time) > 300:
            return jsonify({"error": "Webhook timestamp too old"}), 400
    except ValueError:
        return jsonify({"error": "Invalid timestamp"}), 400

    # 3. Verify HMAC signature
    signature = signature.replace("sha256=", "")  # Remove prefix
    payload = request.get_data(as_text=True)

    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        f"{timestamp}.{payload}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 401

    # 4. Process the webhook
    data = request.json

    event_handlers = {
        "creative_approval": handle_creative_approval,
        "media_buy_status": handle_media_buy_status,
    }

    handler = event_handlers.get(data.get("step_type"))
    if handler:
        handler(data)

    return jsonify({"status": "ok"}), 200


def handle_creative_approval(data):
    """Handle creative approval events."""
    creative_id = data["object_id"]
    status = data["status"]

    if status == "requires_approval":
        print(f"Creative {creative_id} needs approval")
        # Notify your team, update your database, etc.
    elif status == "completed":
        print(f"Creative {creative_id} was approved")
        # Update your system accordingly


def handle_media_buy_status(data):
    """Handle media buy status changes."""
    media_buy_id = data["object_id"]
    status = data["status"]
    print(f"Media buy {media_buy_id} status: {status}")


if __name__ == "__main__":
    app.run(port=3001)
```

### Node.js (Express)

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

// Store this securely
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET;

app.post('/webhooks/adcp', (req, res) => {
  // 1. Get signature and timestamp
  const signature = req.headers['x-webhook-signature'] || '';
  const timestamp = req.headers['x-webhook-timestamp'];

  if (!signature || !timestamp) {
    return res.status(401).json({ error: 'Missing signature headers' });
  }

  // 2. Replay attack prevention
  const webhookTime = parseInt(timestamp);
  if (Math.abs(Date.now() / 1000 - webhookTime) > 300) {
    return res.status(400).json({ error: 'Webhook timestamp too old' });
  }

  // 3. Verify signature
  const payload = JSON.stringify(req.body);
  const expectedSignature = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(`${timestamp}.${payload}`)
    .digest('hex');

  const receivedSignature = signature.replace('sha256=', '');

  if (!crypto.timingSafeEqual(
    Buffer.from(expectedSignature),
    Buffer.from(receivedSignature)
  )) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // 4. Process webhook
  const data = req.body;
  console.log(`Received webhook: ${data.step_type} for ${data.object_id}`);

  // Your business logic here

  res.json({ status: 'ok' });
});

app.listen(3001, () => {
  console.log('Webhook server running on port 3001');
});
```

### Ruby (Sinatra)

```ruby
require 'sinatra'
require 'json'
require 'openssl'

WEBHOOK_SECRET = ENV['WEBHOOK_SECRET']

post '/webhooks/adcp' do
  request.body.rewind
  payload = request.body.read

  # Get headers
  signature = request.env['HTTP_X_WEBHOOK_SIGNATURE']&.sub('sha256=', '')
  timestamp = request.env['HTTP_X_WEBHOOK_TIMESTAMP']

  halt 401, { error: 'Missing signature headers' }.to_json unless signature && timestamp

  # Replay protection
  halt 400, { error: 'Webhook too old' }.to_json if (Time.now.to_i - timestamp.to_i).abs > 300

  # Verify signature
  expected_signature = OpenSSL::HMAC.hexdigest(
    'SHA256',
    WEBHOOK_SECRET,
    "#{timestamp}.#{payload}"
  )

  halt 401, { error: 'Invalid signature' }.to_json unless Rack::Utils.secure_compare(signature, expected_signature)

  # Process webhook
  data = JSON.parse(payload)
  puts "Received webhook: #{data['step_type']} for #{data['object_id']}"

  { status: 'ok' }.to_json
end
```

## Testing Your Webhook

### 1. Test with curl

```bash
# Generate test payload
TIMESTAMP=$(date +%s)
PAYLOAD='{"event":"test","data":"value"}'
SECRET="your_secret"

# Generate signature
SIGNATURE=$(echo -n "${TIMESTAMP}.${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# Send test webhook
curl -X POST http://localhost:3001/webhooks/adcp \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: sha256=${SIGNATURE}" \
  -H "X-Webhook-Timestamp: ${TIMESTAMP}" \
  -d "$PAYLOAD"
```

### 2. Use Webhook Testing Tools

- **ngrok**: Expose localhost to the internet for testing
  ```bash
  ngrok http 3001
  # Use the ngrok URL in Admin UI webhook registration
  ```

- **RequestBin**: Inspect incoming webhooks without code
  - Visit https://requestbin.com
  - Use the generated URL in Admin UI

### 3. Check Logs

Enable detailed logging in your webhook handler to debug issues:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route("/webhooks/adcp", methods=["POST"])
def handle_webhook():
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Payload: {request.get_data(as_text=True)}")
    # ... rest of handler
```

## Best Practices

### 1. Always Verify Signatures in Production

```python
# ❌ DON'T: Skip verification
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json  # UNSAFE!
    process(data)

# ✅ DO: Always verify
@app.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request):
        return {"error": "Invalid signature"}, 401
    data = request.json  # SAFE
    process(data)
```

### 2. Implement Idempotency

Webhooks may be retried, so handle duplicates:

```python
processed_webhooks = set()

def handle_webhook(data):
    step_id = data["step_id"]

    if step_id in processed_webhooks:
        return  # Already processed

    # Process webhook
    do_something(data)

    # Mark as processed
    processed_webhooks.add(step_id)
```

### 3. Respond Quickly

Return HTTP 200 within 10 seconds to avoid timeouts:

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    # Verify signature (fast)
    if not verify_signature(request):
        return {"error": "Invalid"}, 401

    data = request.json

    # Queue for async processing (fast)
    queue.enqueue(process_webhook, data)

    # Return immediately
    return {"status": "ok"}, 200


def process_webhook(data):
    # Do slow operations here (database writes, API calls, etc.)
    pass
```

### 4. Use HTTPS in Production

```python
# ✅ Production webhook URL
https://your-domain.com/webhooks/adcp

# ⚠️ Development only
http://localhost:3001/webhooks/adcp
```

### 5. Log Security Failures

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request):
        logger.warning(
            "Invalid webhook signature",
            extra={
                "ip": request.remote_addr,
                "signature": request.headers.get("X-Webhook-Signature"),
                "timestamp": request.headers.get("X-Webhook-Timestamp"),
            }
        )
        return {"error": "Invalid signature"}, 401
```

## Troubleshooting

### Webhook Not Received

1. Check webhook is **active** in Admin UI
2. Verify URL is accessible from internet (use ngrok for localhost)
3. Check firewall/security group rules
4. Look for webhook delivery logs in operations dashboard

### Signature Verification Fails

1. Ensure you're using the **exact secret** from Admin UI
2. Verify payload hasn't been modified (no extra spaces, encoding issues)
3. Check timestamp is being read correctly
4. Use constant-time comparison (`hmac.compare_digest`)

### Webhooks Timing Out

1. Respond within 10 seconds (queue slow operations)
2. Check endpoint performance/database queries
3. Implement health check endpoint

### Duplicate Webhooks

1. Webhooks may be retried on failures - implement idempotency
2. Use `step_id` to detect duplicates
3. Return 200 even for duplicates

## Support

- **Documentation**: https://docs.sales-agent.scope3.com
- **API Reference**: https://adcontextprotocol.org/docs/
- **Issues**: https://github.com/adcontextprotocol/salesagent/issues

## AdCP Delivery Webhooks (Enhanced Security)

For delivery reporting webhooks (impressions, spend, etc.), see the enhanced webhook service with additional security and reliability features.

### Enhanced Security Features (AdCP PR #86)

The delivery webhook service implements advanced security and reliability:

**Security:**
- HMAC-SHA256 signatures with `X-ADCP-Signature` header
- Replay attack prevention (5-minute window)
- Minimum 32-character secrets required
- Constant-time signature comparison

**Reliability:**
- Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN states)
- Exponential backoff with jitter
- Bounded queues (1000 webhooks per endpoint)
- Per-endpoint isolation

**New Payload Fields:**
- `is_adjusted`: Boolean flag for late-arriving data corrections
- `notification_type`: `"scheduled"`, `"final"`, or `"adjusted"`

### Using Enhanced Delivery Webhooks

```python
from src.services.webhook_delivery_service_v2 import enhanced_webhook_delivery_service

# Send delivery webhook with security
enhanced_webhook_delivery_service.send_delivery_webhook(
    media_buy_id="buy_123",
    tenant_id="tenant_1",
    principal_id="buyer_1",
    reporting_period_start=datetime(2025, 10, 1, tzinfo=UTC),
    reporting_period_end=datetime(2025, 10, 2, tzinfo=UTC),
    impressions=100000,
    spend=500.00,
    is_adjusted=False,  # True for late-arriving data
)
```

### Verifying Delivery Webhooks

```python
from src.services.webhook_verification import verify_adcp_webhook, WebhookVerificationError

@app.post("/webhooks/adcp/delivery")
def receive_delivery_webhook(request):
    try:
        # Verify signature and timestamp
        verify_adcp_webhook(
            webhook_secret="your-32-char-secret",
            payload=request.json(),
            request_headers=dict(request.headers)
        )

        # Process verified webhook
        data = request.json()
        if data.get("is_adjusted"):
            # Update historical data
            update_delivery_data(data)
        else:
            # Add new delivery data
            record_delivery_data(data)

        return {"status": "success"}

    except WebhookVerificationError as e:
        logger.warning(f"Invalid webhook: {e}")
        return {"error": str(e)}, 401
```

### Circuit Breaker Monitoring

```python
# Check endpoint health
state, failures = enhanced_webhook_delivery_service.get_circuit_breaker_state(
    "https://buyer.example.com/webhooks"
)

# Manual recovery if needed
enhanced_webhook_delivery_service.reset_circuit_breaker(
    "https://buyer.example.com/webhooks"
)
```

For complete documentation on delivery webhook security, see the implementation in:
- `src/services/webhook_delivery_service_v2.py`
- `src/services/webhook_verification.py`

## Changelog

- **2025-10-09**: Added enhanced delivery webhooks with circuit breakers and HMAC-SHA256 (AdCP PR #86)
- **2025-10-04**: Added HMAC-SHA256 authentication support
- **2025-10-04**: Added SSRF protection for webhook URLs
- **2025-09-15**: Initial webhook support
