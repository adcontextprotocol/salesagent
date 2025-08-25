# Using Standard python-a2a Library with Authentication

## Summary

The AdCP Sales Agent A2A server now supports authenticated requests from the **standard python-a2a library** without requiring any custom code. This is achieved through query parameter authentication, which is fully compatible with the library's URL handling.

## Quick Start

### Using the Standard CLI (python-a2a)

The simplest way to use the standard library with authentication is to include the token as a query parameter:

```bash
# Install python-a2a if not already installed
pip install python-a2a

# Use the standard CLI with token in URL
python -m python_a2a.cli send "http://localhost:8091?token=demo_token_123" "What products do you have?"
```

### Using Standard Python Code

```python
from python_a2a import A2AClient, create_text_message, pretty_print_message

# Token is included in the URL as a query parameter
client = A2AClient("http://localhost:8091?token=demo_token_123")

# Use standard library methods
message = create_text_message("What products do you have?")
response = client.send_message(message)
pretty_print_message(response)
```

## How It Works

1. **No Custom Code Required**: The standard python-a2a library is used as-is
2. **Query Parameter Authentication**: Token is passed in the URL (`?token=YOUR_TOKEN`)
3. **Server-Side Validation**: The A2A server validates the token against the database
4. **Tenant Isolation**: Each token is tied to a specific advertiser and tenant

## Available Tokens

For local development, use the demo token:
- Token: `demo_token_123`
- Advertiser: Demo Advertiser

To create new tokens:
1. Access Admin UI: http://localhost:8001
2. Navigate to Advertisers
3. Create or view tokens

## Production Usage

For production on Fly.io:
```python
client = A2AClient("https://adcp-sales-agent.fly.dev/a2a?token=YOUR_PROD_TOKEN")
```

## Why This Approach?

The python-a2a library's `A2AClient` class hardcodes headers in its implementation, making it impossible to add authentication headers without modifying the library. By supporting query parameter authentication, we achieve:

1. **100% Standard Library Compatibility**: No custom code or library modifications
2. **Simple Integration**: Just append `?token=` to the URL
3. **Works with CLI and Python**: Same approach for both use cases
4. **No Library Forking**: Avoids maintenance burden of custom libraries

## Security Considerations

- **HTTPS in Production**: Always use HTTPS when passing tokens in URLs
- **Token Rotation**: Regularly rotate tokens in production
- **Logging**: Be careful not to log URLs containing tokens
- **Alternative Methods**: For enhanced security, consider using a proxy that adds headers

## Testing

```bash
# Test with curl (query parameter)
curl -X POST "http://localhost:8091/tasks/send?token=demo_token_123" \
  -H "Content-Type: application/json" \
  -d '{"message": {"content": {"text": "What products do you have?"}}}'

# Test with standard python-a2a CLI
python -m python_a2a.cli send "http://localhost:8091?token=demo_token_123" \
  "What products do you have for video advertising?"
```

Both approaches use the standard library without any custom code!
