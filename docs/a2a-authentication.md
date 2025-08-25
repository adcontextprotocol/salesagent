# A2A Authentication Guide

## Security First

**Important**: Always use Authorization headers for authentication. Never put tokens in URLs in production as they can be logged, cached, and exposed in browser history.

## Quick Start

### Recommended: Use the Provided Script

```bash
# Default token (demo_token_123)
./scripts/a2a_query.py "What products do you have?"

# Custom token via environment variable
A2A_TOKEN=demo_token_123 ./scripts/a2a_query.py "Show me video ads"

# Production usage
A2A_ENDPOINT=https://adcp-sales-agent.fly.dev/a2a \
A2A_TOKEN=your_production_token \
./scripts/a2a_query.py "What products?"
```

### Alternative: Use curl Directly

```bash
# Send authenticated request with Bearer token (secure)
curl -X POST "http://localhost:8091/tasks/send" \
  -H "Authorization: Bearer demo_token_123" \
  -H "Content-Type: application/json" \
  -d '{"message": {"content": {"text": "What products do you have?"}}}'
```

## Why Not Use python-a2a CLI Directly?

The standard `python-a2a` CLI has limitations:
- Doesn't support adding custom headers for authentication
- URL query parameters get mangled when it appends `/tasks/send`
- No way to pass authentication tokens securely

Our `a2a_query.py` script solves these issues by using secure Authorization headers.

## Authentication Methods

The server supports these authentication methods (in order of security preference):

1. **Authorization Header** `Authorization: Bearer TOKEN` - Most secure, recommended
2. **Custom Header** `X-Auth-Token: TOKEN` - Secure alternative
3. **Query Parameter** `?token=TOKEN` - Less secure, avoid in production
4. **Environment Variable** `A2A_AUTH_TOKEN` - Server-side fallback only

**Production Rule**: Always use Authorization headers.

## Available Tokens

### Local Development
- Token: `demo_token_123`
- Advertiser: Demo Advertiser

### Getting New Tokens
1. Access Admin UI: http://localhost:8001
2. Navigate to Advertisers
3. Create new advertiser or copy existing token

## Writing Your Own Client

```python
import requests
import json

# Your authentication token
TOKEN = "demo_token_123"
ENDPOINT = "http://localhost:8091"

# Send request with secure Authorization header
response = requests.post(
    f"{ENDPOINT}/tasks/send",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "message": {
            "content": {"text": "What products do you have?"}
        }
    }
)

# Parse response
data = response.json()
for artifact in data.get("artifacts", []):
    for part in artifact.get("parts", []):
        if part.get("type") == "text":
            print(part["text"])
```

## Examples

```bash
# Query products
./scripts/a2a_query.py "What products do you have?"

# Create a campaign
./scripts/a2a_query.py "Create a video ad campaign with $5000 budget for next month"

# Check targeting options
./scripts/a2a_query.py "What targeting options are available for sports content?"

# Get pricing information
./scripts/a2a_query.py "What are the CPM rates for video ads?"
```

## Security Best Practices

1. **Never put tokens in URLs** - They appear in logs and browser history
2. **Use HTTPS in production** - Encrypts tokens in transit
3. **Rotate tokens regularly** - Minimize exposure if compromised
4. **Use environment variables** - Don't hardcode tokens in scripts
5. **Monitor access logs** - Watch for unauthorized attempts

## Troubleshooting

### 401 Unauthorized
- Check token is valid: `demo_token_123` for local development
- Ensure you're using the Authorization header, not URL parameters
- Verify token hasn't been revoked in Admin UI

### Connection Refused
- Check Docker is running: `docker ps`
- Verify port 8091 is mapped in docker-compose.yml
- Check A2A server logs: `docker logs boston-adcp-server-1 | grep A2A`

### Invalid Response Format
- Ensure you're sending to `/tasks/send` endpoint
- Message must be in A2A format: `{"message": {"content": {"text": "..."}}}`
- Check server logs for detailed error messages
