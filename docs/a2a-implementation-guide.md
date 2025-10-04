# A2A Implementation Guide

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
# Agent's setup_routes() is called automatically by create_flask_app()
```

## Standard A2A Endpoints

When using `create_flask_app()`, you automatically get these A2A spec-compliant endpoints:

- **`/.well-known/agent.json`** - Standard agent discovery endpoint (A2A spec requirement)
- **`/agent.json`** - Agent card endpoint
- **`/a2a`** - Main A2A endpoint with UI/JSON content negotiation
- **`/`** - Root endpoint (redirects to A2A info)
- **`/stream`** - Server-sent events streaming endpoint
- **`/a2a/health`** - Library's health check
- **CORS support** - Proper headers for browser compatibility
- **OPTIONS handling** - CORS preflight support

## Custom Route Integration

Your custom routes are added via `setup_routes(app)` which is called automatically:

```python
class MyA2AAgent(A2AServer):
    def setup_routes(self, app):
        """Add custom routes to the standard A2A Flask app."""

        # Don't redefine standard routes - they're already provided
        # ❌ Don't add: /agent.json, /.well-known/agent.json, /a2a, etc.

        # ✅ Add your custom business logic routes
        @app.route("/custom/endpoint", methods=["POST"])
        @self.require_auth
        def custom_business_logic():
            return jsonify({"custom": "response"})
```

## Function Naming Conflicts

### ❌ Avoid These Function Names
- `health_check` (conflicts with library's `/a2a/health`)
- `get_agent_card` (conflicts with standard agent card handling)
- `handle_request` (conflicts with library's request handling)

### ✅ Use Descriptive Names
```python
@app.route("/health", methods=["GET"])
def custom_health_check():  # Different from library's health_check
    return jsonify({"status": "healthy"})
```

## A2A Agent Card Structure

Ensure your agent card includes all required A2A fields:

```python
agent_card = AgentCard(
    name="Your Agent Name",
    description="Clear description of agent capabilities",
    url="http://your-server:port",
    version="1.0.0",
    authentication="bearer-token",  # REQUIRED for auth
    skills=[
        AgentSkill(name="skill1", description="What skill1 does"),
        AgentSkill(name="skill2", description="What skill2 does"),
    ],
    capabilities={
        "google_a2a_compatible": True,  # REQUIRED for Google A2A clients
        "parts_array_format": True,     # REQUIRED for Google A2A clients
    }
)
```

## Testing Requirements

**ALWAYS** add these tests when implementing A2A servers:

```python
def test_well_known_agent_json_endpoint(client):
    """Test A2A spec compliance - agent discovery."""
    response = client.get('/.well-known/agent.json')
    assert response.status_code == 200
    data = response.get_json()
    assert 'name' in data
    assert 'skills' in data

def test_standard_a2a_endpoints(client):
    """Test all standard A2A endpoints exist."""
    endpoints = ['/.well-known/agent.json', '/agent.json', '/a2a', '/stream']
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code != 404  # Should exist
```

## Nginx Configuration

**When using `create_flask_app()`, you don't need nginx workarounds:**

```nginx
# ❌ Don't add these - library provides standard endpoints automatically
# location /.well-known/agent-card.json { ... }  # Wrong endpoint name anyway
# location /.well-known/agent.json { ... }       # Library handles this

# ✅ Just proxy to A2A server - it handles standard endpoints
location /a2a/ {
    proxy_pass http://a2a_backend;
    # Standard proxy headers...
}
```

## Deployment Checklist

Before deploying A2A servers:

1. ✅ **Use `create_flask_app(agent)`** - not custom Flask app
2. ✅ **Test `/.well-known/agent.json`** - should return 200 with agent card
3. ✅ **Test agent card structure** - includes name, skills, authentication
4. ✅ **Test Bearer token auth** - protected endpoints reject invalid tokens
5. ✅ **Test CORS headers** - client browsers can access endpoints
6. ✅ **Run regression tests** - prevent future breaking changes
7. ✅ **Verify with A2A client** - can discover and communicate with agent

## Troubleshooting

### Issue: "404 NOT FOUND" for `/.well-known/agent-card.json`
- **Cause**: Using custom Flask app instead of `create_flask_app()`
- **Fix**: Use `create_flask_app(agent)`

### Issue: "View function mapping is overwriting an existing endpoint"
- **Cause**: Function name conflicts with library functions
- **Fix**: Use unique function names (e.g., `custom_health_check` not `health_check`)

### Issue: A2A clients can't discover agent
- **Cause**: Missing `/.well-known/agent.json` endpoint
- **Fix**: Ensure using `create_flask_app()` and agent card has required fields

### Issue: Authentication not working
- **Cause**: Agent card doesn't specify `authentication="bearer-token"`
- **Fix**: Add authentication field to AgentCard constructor

## See Also

- [A2A Regression Prevention](testing/a2a-regression-prevention.md)
- [A2A Authentication Guide](a2a-authentication-guide.md)
- [A2A Overview](a2a-overview.md)
