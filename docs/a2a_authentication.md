# A2A Server Authentication Guide

## Overview

The AdCP Sales Agent A2A server requires authentication to ensure tenant isolation and security. Each request must include a valid access token that corresponds to a principal (advertiser) in the database.

## Authentication Methods

The server accepts authentication tokens via three standard methods:

### 1. Authorization Header (Recommended)
```bash
curl -X POST http://localhost:8091/tasks/send \
  -H "Authorization: Bearer test_token_1" \
  -H "Content-Type: application/json" \
  -d '{"message": "What products do you have?"}'
```

### 2. Custom Header
```bash
curl -X POST http://localhost:8091/tasks/send \
  -H "X-Auth-Token: test_token_1" \
  -H "Content-Type: application/json" \
  -d '{"message": "What products do you have?"}'
```

### 3. Query Parameter (For Compatibility)
```bash
curl -X POST "http://localhost:8091/tasks/send?token=test_token_1" \
  -H "Content-Type: application/json" \
  -d '{"message": "What products do you have?"}'
```

## Using with Standard python-a2a Library

The standard `python-a2a` library's `A2AClient` class doesn't natively support authentication headers. However, you can use the library with authentication through these approaches:

### Option 1: Environment Variable (Recommended for Standard Library)

The cleanest way to use the standard library without modification is to have the server check an environment variable as a fallback:

```python
# Set environment variable
import os
os.environ['A2A_AUTH_TOKEN'] = 'test_token_1'

# Use standard library
from python_a2a import A2AClient, create_text_message
client = A2AClient("http://localhost:8091")
message = create_text_message("What products do you have?")
response = client.send_message(message)
```

### Option 2: Proxy Pattern

For production use, consider running a local proxy that adds authentication headers:

```bash
# Example using nginx or similar proxy
# Proxy adds "Authorization: Bearer YOUR_TOKEN" to all requests
```

### Option 3: Subclass A2AClient (If Customization is Acceptable)

If minimal customization is acceptable, you can subclass the standard client:

```python
from python_a2a import A2AClient
import requests

class AuthenticatedA2AClient(A2AClient):
    def __init__(self, endpoint_url, token):
        super().__init__(endpoint_url)
        self.token = token

    def send_message(self, message):
        # Override to add authentication
        response = requests.post(
            f"{self.endpoint_url}/tasks/send",
            json=message.to_dict(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}"
            }
        )
        response.raise_for_status()
        return Message.from_dict(response.json())
```

## Token Management

### Getting Tokens

Tokens are managed through the Admin UI:
1. Navigate to http://localhost:8001
2. Select your tenant
3. Go to "Advertisers" (Principals)
4. View or create tokens for each advertiser

### Token Format

Tokens are alphanumeric strings (e.g., `test_token_1`, `prod_abc123xyz`)

### Token Security

- Keep tokens secure and never commit them to version control
- Each token is tied to a specific principal and tenant
- Tokens provide complete access to that principal's resources
- Rotate tokens regularly in production

## Testing Authentication

### Quick Test (Public Endpoint)
```bash
# This should work without authentication
curl http://localhost:8091/
```

### Authenticated Test
```bash
# This requires valid authentication
curl -X POST http://localhost:8091/tasks/send \
  -H "Authorization: Bearer test_token_1" \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

## Production Deployment

For production on Fly.io:
- URL: https://adcp-sales-agent.fly.dev/a2a
- Same authentication methods apply
- Use HTTPS for all requests
- Consider implementing rate limiting

## Troubleshooting

### 401 Unauthorized
- Check token is valid in database
- Ensure token is being sent correctly
- Verify tenant and principal exist

### 500 Internal Server Error
- Check server logs: `docker-compose logs adcp-server`
- Verify database connection
- Ensure tenant configuration is valid

## Standard Library Limitations

The `python-a2a` library's `A2AClient` class has these limitations:
1. Headers are hardcoded in the `send_message` method
2. No built-in authentication support
3. URL construction doesn't preserve query parameters

These are inherent to the library design. The recommended approach is to use environment variables or a proxy for production deployments requiring the standard library.
