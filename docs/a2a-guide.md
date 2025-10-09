# A2A (Agent-to-Agent) Protocol Guide

## Overview

The AdCP Sales Agent implements the A2A protocol using the standard `python-a2a` library, allowing AI agents to query advertising inventory and create media buys programmatically.

## Server Implementation

- **Library**: Standard `python-a2a` with custom business logic
- **Location**: `src/a2a_server/adcp_a2a_server.py`
- **Port**: 8091 (local), available at `/a2a` path in production
- **Protocol**: JSON-RPC 2.0 compliant with string `messageId` (per spec)
- **Authentication**: Required via Bearer tokens
- **Backward Compatibility**: Middleware converts numeric messageId to string for legacy clients

---

# Authentication

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
./scripts/a2a_query.py "What products are available?"
```

### Using curl

```bash
# Query products
curl -X POST "http://localhost:8091/tasks/send" \
  -H "Authorization: Bearer demo_token_123" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "parts": [{
        "type": "text",
        "text": "What products do you have?"
      }]
    }
  }'

# Create campaign
curl -X POST "http://localhost:8091/tasks/send" \
  -H "Authorization: Bearer demo_token_123" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "parts": [{
        "type": "text",
        "text": "Create a video ad campaign with $5000 budget for next month"
      }]
    }
  }'
```

## Getting Tokens

1. Access Admin UI: http://localhost:8001
2. Navigate to "Advertisers"
3. Create new advertiser or copy existing token

## Token Security

- ✅ Use Authorization header: `Authorization: Bearer token`
- ❌ Never in URL: `http://api.example.com/endpoint?token=...`
- ✅ Environment variables: `A2A_TOKEN=...`
- ✅ Secure storage: Use secrets manager in production

---

# Implementation Guide

## Critical: Always Use `create_flask_app()`

### Problem
Custom Flask app creation bypasses standard A2A protocol endpoints.

### ❌ WRONG - Custom Flask App
```python
# This bypasses standard A2A endpoints
from flask import Flask
app = Flask(__name__)
agent.setup_routes(app)
```

### ✅ CORRECT - Standard Library App
```python
# This provides all standard A2A endpoints automatically
from python_a2a.server.http import create_flask_app
app = create_flask_app(agent)
```

### Why It Matters

The `python-a2a` library provides essential protocol endpoints:
- `/tasks/send` - Send new task
- `/tasks/{task_id}` - Get task status
- `/tasks/{task_id}/cancel` - Cancel task
- `/skills` - List available skills
- `/health` - Health check

Using `create_flask_app()` ensures:
1. **Protocol compliance** - All required endpoints present
2. **Standard behavior** - Clients work without custom handling
3. **Future compatibility** - New protocol features automatic
4. **Less code** - No need to manually register routes

## Correct Implementation Pattern

```python
from python_a2a import Agent
from python_a2a.server.http import create_flask_app

# Create agent with skills
agent = Agent(
    name="AdCP Sales Agent",
    description="Advertising inventory sales agent",
)

# Register skills
@agent.skill("get_products")
async def get_products_skill(brief: str = "") -> dict:
    # Implementation...
    pass

# Create Flask app with all standard endpoints
app = create_flask_app(agent)

# Add custom routes if needed (after standard routes)
@app.route('/custom/endpoint')
def custom_endpoint():
    return {"status": "ok"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8091)
```

## Testing

```bash
# Verify all standard endpoints are present
curl http://localhost:8091/health
curl http://localhost:8091/skills

# Test task creation
curl -X POST http://localhost:8091/tasks/send \
  -H "Authorization: Bearer token" \
  -H "Content-Type: application/json" \
  -d '{"message": {"parts": [{"type": "text", "text": "Hello"}]}}'
```

---

# Integration with MCP

The A2A server acts as a bridge to the MCP (Model Context Protocol) backend:

1. Receives natural language queries via A2A protocol
2. Authenticates the advertiser
3. Calls appropriate MCP tools with proper context
4. Returns tenant-specific products and information

## Supported Queries

The A2A server responds intelligently to natural language queries about:
- Available advertising products and inventory
- Pricing and CPM rates
- Targeting options
- Campaign creation requests

## Example Queries

```bash
# Query products
./scripts/a2a_query.py "What products do you have?"

# Query with filters
./scripts/a2a_query.py "Show me video ads under $50 CPM"

# Create campaign
./scripts/a2a_query.py "Create a video ad campaign with $5000 budget for next month"

# Check delivery
./scripts/a2a_query.py "What's the status of media buy mb_12345?"
```

---

# Production Deployment

## Environment Variables

```bash
# Required
A2A_ENDPOINT=https://your-domain.com/a2a
A2A_TOKEN=your_production_token

# Optional
A2A_TIMEOUT=30  # Request timeout in seconds
```

## Production Example

```bash
# Query production API
A2A_ENDPOINT=https://adcp-sales-agent.fly.dev/a2a \
A2A_TOKEN=production_token \
./scripts/a2a_query.py "What products are available?"
```

## Best Practices

1. **Authentication**: Always use Bearer tokens via Authorization header
2. **HTTPS**: Use HTTPS in production (enforce SSL)
3. **Rate Limiting**: Implement rate limits per token
4. **Logging**: Log all requests for audit trail
5. **Monitoring**: Monitor task completion rates and errors

---

# Troubleshooting

## Authentication Errors

**Error**: `401 Unauthorized`

**Solutions**:
1. Check token is valid in Admin UI
2. Verify `Authorization: Bearer token` header format
3. Ensure token is for correct tenant

## Connection Errors

**Error**: `Connection refused`

**Solutions**:
1. Verify server is running: `docker-compose ps`
2. Check port 8091 is accessible
3. Check firewall rules

## Invalid Response Format

**Error**: Protocol compliance errors

**Solutions**:
1. Ensure using `create_flask_app(agent)` not custom Flask app
2. Check `python-a2a` library version is up to date
3. Verify messageId is string not number

---

# References

- A2A Protocol Spec: https://github.com/CopilotKit/A2A
- python-a2a Library: https://github.com/CopilotKit/python-a2a
- AdCP Protocol: https://adcontextprotocol.org/docs/
