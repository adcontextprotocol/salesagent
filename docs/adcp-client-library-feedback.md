# Feedback for `adcp` Python Client Library

**Date**: 2025-11-05
**From**: AdCP Sales Agent Reference Implementation Team
**Version Reviewed**: v0.1.2
**Context**: Real-world production usage patterns for signals and creative agents

---

## Executive Summary

Overall, the library is **excellent** and solves real problems we face. Below is detailed feedback based on our actual implementation patterns, edge cases we've encountered, and production requirements.

---

## 🎯 Critical Features Needed

### 1. **Custom Auth Header Support** ⚠️ HIGH PRIORITY

**Problem**: Many agents use custom auth header names (not just "Authorization")

**Real-world example** (Optable signals agent):
```python
# Their configuration:
auth_header = "Authorization"  # Not "x-api-key"
auth_type = "bearer"
credentials = "5ZWQoDY8sReq7CTNQdgPokHdEse8JB2LDjOfo530_9A="

# Expected header:
Authorization: Bearer 5ZWQoDY8sReq7CTNQdgPokHdEse8JB2LDjOfo530_9A=
```

**Current library API** (from README):
```python
AgentConfig(
    id="agent_x",
    agent_uri="https://agent-x.com",
    protocol="a2a",
    auth_token="token"  # ❌ No way to specify custom header name
)
```

**Requested API**:
```python
AgentConfig(
    id="optable",
    agent_uri="https://sandbox.optable.co/admin/adcp/signals/mcp",
    protocol="mcp",
    auth_type="bearer",  # ✅ Format: "Bearer {token}"
    auth_token="5ZWQ...",
    auth_header="Authorization"  # ✅ Custom header name
)
```

**Why this matters**:
- Different vendors use different header names
- Some use "Authorization", others use "X-API-Key", "X-Custom-Auth", etc.
- Can't connect to agents without custom header support
- This is a **blocker** for adoption

**Implementation suggestion**:
```python
@dataclass
class AgentConfig:
    id: str
    agent_uri: str
    protocol: Literal["mcp", "a2a"]
    auth_token: str | None = None
    auth_type: Literal["bearer", "api_key", "basic"] | None = None  # NEW
    auth_header: str | None = None  # NEW - overrides default header name
```

---

### 2. **URL Path Handling with Fallback** 🔧 MEDIUM PRIORITY

**Problem**: Different agents use different URL conventions

**Real-world URLs we've encountered**:
```
https://creative.adcontextprotocol.org/mcp          ✅ Explicit /mcp
https://creative.adcontextprotocol.org              ❓ Base URL (should try /mcp)
https://audience-agent.fly.dev/FastMCP/             ❓ Different path
https://sandbox.optable.co/admin/adcp/signals/mcp   ✅ Deep path with /mcp
```

**Our current implementation** (works well):
```python
# src/core/utils/mcp_client.py:148-157
primary_url = agent_url.rstrip("/")
fallback_url = None
if not primary_url.endswith("/mcp"):
    fallback_url = f"{primary_url}/mcp"

candidates = [(primary_url, max_retries)]
if fallback_url:
    candidates.append((fallback_url, 1))  # Try fallback after primary fails
```

**Why this matters**:
- Users often forget to add "/mcp" suffix
- Some agents document base URL only
- Reduces support burden ("connection failed" tickets)
- Makes library more forgiving

**Requested behavior**:
1. Try user's exact URL first (with retries)
2. If all retries fail AND URL doesn't end with "/mcp", try appending "/mcp" once
3. Clear error message if both fail

---

### 3. **MCP SDK Compatibility Detection** 🔍 MEDIUM PRIORITY

**Problem**: Different FastMCP versions have breaking changes

**Real error we've seen**:
```
Exception: Unsupported notification: notifications/initialized
```

**Our current implementation**:
```python
# src/core/utils/mcp_client.py:186-197
if "notifications/initialized" in error_msg:
    raise MCPCompatibilityError(
        f"MCP SDK compatibility issue: "
        f"Server doesn't support notifications/initialized. "
        f"The agent may need to upgrade their FastMCP version."
    )
```

**Why this matters**:
- FastMCP is evolving rapidly
- Some agents run older versions
- Need clear error messages for debugging
- Helps agent operators fix their servers

**Requested feature**:
- Detect known MCP compatibility issues
- Raise specific exception type (e.g., `MCPVersionMismatchError`)
- Include helpful error message with upgrade instructions
- Optional: Version negotiation (if MCP protocol supports it)

---

### 4. **Connection Health Check / Test Connection** 🩺 MEDIUM PRIORITY

**Use case**: Admin UI "Test Connection" buttons

**Our current implementation**:
```python
# src/core/utils/mcp_client.py:223-280
async def check_mcp_agent_connection(
    agent_url: str,
    auth: dict | None = None,
    auth_header: str | None = None
) -> dict[str, Any]:
    """Test connection and return diagnostic info."""
    try:
        async with create_mcp_client(...) as client:
            tools = await client.list_tools()
            return {
                "success": True,
                "message": "Connected",
                "tool_count": len(tools)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**Why this matters**:
- Users need to verify agent configuration
- Helps debug auth issues
- Reduces "why isn't it working" support tickets

**Requested API**:
```python
from adcp import ADCPMultiAgentClient

client = ADCPMultiAgentClient(...)

# Test specific agent connection
result = await client.agent("agent_id").test_connection()
# Returns: {"success": bool, "message": str, "capabilities": [...]}
```

---

### 5. **Per-Agent Timeout Configuration** ⏱️ LOW PRIORITY

**Use case**: Different agents have different latency characteristics

**Our database schema**:
```python
class SignalsAgent(Base):
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    # ^^ Configurable per-agent
```

**Why this matters**:
- Signals agents may do heavy computation (60+ seconds)
- Creative agents are fast (5-10 seconds)
- One timeout doesn't fit all

**Current workaround**: Can probably pass timeout in call kwargs?

**Requested API**:
```python
AgentConfig(
    id="slow_signals_agent",
    agent_uri="...",
    protocol="mcp",
    timeout=90  # ✅ Per-agent timeout
)
```

---

### 6. **Graceful Degradation / Fallback Behavior** 🛟 LOW PRIORITY

**Use case**: Continue if one agent fails

**Our current implementation**:
```python
# src/core/signals_agent_registry.py:228-244
for agent in agents:
    try:
        signals = await self._get_signals_from_agent(agent, ...)
        all_signals.extend(signals)
    except Exception as e:
        logger.error(f"Failed to fetch from {agent.url}: {e}")
        continue  # ✅ Don't fail entire request if one agent down
```

**Why this matters**:
- Multi-agent setups should be resilient
- One bad agent shouldn't break everything
- Partial results are better than no results

**Requested behavior**:
```python
# When calling multiple agents in parallel
results = await client.get_signals(brief="test")

# Should return partial success:
# results = [
#   {"agent_id": "agent_1", "status": "completed", "data": {...}},
#   {"agent_id": "agent_2", "status": "failed", "error": "Connection timeout"},
# ]
```

---

## 📚 Documentation Requests

### 1. **Migration Guide from FastMCP Client**

**What we need**:
- Step-by-step guide for migrating from direct FastMCP usage
- Code comparison examples (before/after)
- Common pitfalls and solutions

**Example content**:
```markdown
## Migrating from FastMCP Client

### Before (FastMCP)
```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"Authorization": f"Bearer {token}"}
transport = StreamableHttpTransport(url=agent_url, headers=headers)
client = Client(transport=transport)

async with client:
    result = await client.call_tool("get_signals", params)
```

### After (adcp)
```python
from adcp import ADCPMultiAgentClient
from adcp.types import AgentConfig

client = ADCPMultiAgentClient(agents=[
    AgentConfig(
        id="signals_agent",
        agent_uri=agent_url,
        protocol="mcp",
        auth_token=token
    )
])

result = await client.agent("signals_agent").get_signals(**params)
```

### Key Differences
- ✅ No manual header building
- ✅ Type-safe responses
- ✅ Built-in retry logic
- ✅ Webhook support included
```

---

### 2. **Real-World Configuration Examples**

**What we need**: Production-ready config examples for:
- Optable signals agent
- AdCP creative agent
- Custom creative agent (DCO platform)
- Multi-tenant setup (different agents per tenant)

**Example**:
```python
# Example: Optable Signals Agent
AgentConfig(
    id="optable_signals",
    agent_uri="https://sandbox.optable.co/admin/adcp/signals/mcp",
    protocol="mcp",
    auth_type="bearer",
    auth_token=os.getenv("OPTABLE_API_KEY"),
    auth_header="Authorization"
)
```

---

### 3. **Error Handling Best Practices**

**What we need**:
- List of all exception types
- When each exception is raised
- Recommended handling patterns
- Retry strategies

**Example**:
```markdown
## Exception Hierarchy

```
ADCPError (base)
├── ConnectionError (network/timeout)
├── AuthenticationError (401/403)
├── ProtocolError (MCP/A2A protocol issues)
│   ├── MCPVersionMismatchError
│   └── A2AInvalidResponseError
├── ValidationError (bad request/response)
└── WebhookError (webhook delivery/signature)
```

## Handling Patterns

```python
try:
    result = await client.agent("signals").get_signals(...)
except adcp.AuthenticationError:
    # Check credentials, refresh token
    pass
except adcp.ConnectionError:
    # Retry with backoff or fallback
    pass
except adcp.ValidationError as e:
    # Log schema mismatch, alert on breaking changes
    logger.error(f"Schema validation failed: {e}")
```
```

---

### 4. **Type Stubs / API Reference**

**What we need**:
- Full type stubs for IDE autocomplete
- Docstrings on all public APIs
- Response model documentation

**Example**:
```python
class ADCPMultiAgentClient:
    """Multi-agent AdCP client.

    Args:
        agents: List of agent configurations
        webhook_url_template: Template for webhook URLs (optional)
        webhook_secret: Secret for HMAC signature verification (optional)
        on_activity: Callback for all agent events (optional)

    Example:
        >>> client = ADCPMultiAgentClient(agents=[...])
        >>> result = await client.agent("agent_1").get_products(brief="test")
    """

    def agent(self, agent_id: str) -> AgentClient:
        """Get specific agent client by ID.

        Args:
            agent_id: Agent identifier from AgentConfig

        Returns:
            AgentClient for the specified agent

        Raises:
            KeyError: If agent_id not found in configuration
        """
```

---

## 🐛 Potential Issues / Edge Cases

### 1. **Thread Safety / Concurrent Requests**

**Question**: Is `ADCPMultiAgentClient` thread-safe?

**Our use case**:
- FastAPI server handles multiple concurrent requests
- Each request may call multiple signals agents
- Multiple tenants with different agent configurations

**Concern**: Client connection pooling and state management

**Request**: Clarify in docs whether:
- Client can be shared across requests (global singleton)
- Client should be created per-request
- Connection pooling behavior
- Concurrency limits per agent

---

### 2. **Large Response Handling**

**Scenario**: Agent returns 10,000+ signals

**Questions**:
- Does library stream responses?
- Memory limits?
- Pagination support?

**Our workaround**: Apply limits in agent call params

---

### 3. **Webhook Reliability**

**Scenario**: Webhook delivery fails (network issue, server down)

**Questions**:
- Does library retry webhook delivery?
- How to handle missed webhooks?
- Polling fallback pattern?

**Request**: Documentation on webhook reliability guarantees

---

## 🚀 Nice-to-Have Features

### 1. **Built-in Caching**

**Use case**: Creative format list rarely changes

**Our current implementation**:
```python
# src/core/creative_agent_registry.py:42-46
@dataclass
class CachedFormats:
    formats: list[Format]
    fetched_at: datetime
    ttl_seconds: int = 3600  # 1 hour cache
```

**Requested API**:
```python
AgentConfig(
    id="creative_agent",
    agent_uri="...",
    protocol="mcp",
    cache_ttl=3600  # ✅ Built-in caching
)

# First call: hits agent
formats1 = await client.agent("creative_agent").list_creative_formats()

# Second call within TTL: cached
formats2 = await client.agent("creative_agent").list_creative_formats()
```

---

### 2. **Request/Response Logging**

**Use case**: Debug agent communication issues

**Requested API**:
```python
client = ADCPMultiAgentClient(
    agents=[...],
    log_requests=True,  # ✅ Log all requests
    log_responses=True,  # ✅ Log all responses
    log_level="DEBUG"
)
```

---

### 3. **Metrics/Observability**

**Use case**: Production monitoring

**Requested feature**:
```python
# Built-in metrics
client.get_metrics()
# Returns:
# {
#   "agent_1": {
#     "total_requests": 1234,
#     "success_rate": 0.98,
#     "avg_latency_ms": 250,
#     "errors": {"timeout": 12, "auth": 3}
#   }
# }
```

---

### 4. **Protocol Auto-Detection**

**Use case**: Don't want to specify protocol manually

**Current API**:
```python
AgentConfig(protocol="mcp")  # ❌ Must specify
```

**Requested API**:
```python
AgentConfig(
    id="agent",
    agent_uri="https://agent.com",
    # protocol auto-detected by probing agent
)
```

**Implementation**: Try MCP first, fallback to A2A, cache result

---

## 💡 API Design Suggestions

### 1. **Builder Pattern for AgentConfig**

**Readability improvement**:

```python
# Instead of:
AgentConfig(
    id="agent",
    agent_uri="https://...",
    protocol="mcp",
    auth_type="bearer",
    auth_token="token",
    auth_header="Authorization",
    timeout=60
)

# Consider:
AgentConfig.builder()
    .id("agent")
    .uri("https://...")
    .mcp()  # Protocol
    .bearer_auth("token", header="Authorization")
    .timeout(60)
    .build()
```

**Benefits**: More readable, discoverable, chainable

---

### 2. **Context Manager for Client**

**Resource management**:

```python
# Support context manager
async with ADCPMultiAgentClient(agents=[...]) as client:
    result = await client.agent("agent_1").get_signals(...)
# ✅ Automatic cleanup on exit
```

---

### 3. **Typed Tool Methods**

**Current** (from README):
```python
result = await agent.get_signals(brief="test")
# Type hint: TaskResult[???]  # What's the response type?
```

**Suggestion**: Clear response type hints
```python
result = await agent.get_signals(brief="test")
# Type hint: TaskResult[GetSignalsResponse]  # ✅ Clear type
```

---

## 🎯 Priority Summary

### Must-Have (Blockers for Adoption)
1. ⚠️ **Custom auth header support** - Can't use library without this
2. 🔧 **URL path fallback** - Reduces user friction significantly

### Should-Have (High Value)
3. 🔍 **MCP compatibility detection** - Better error messages
4. 🩺 **Connection health check** - Essential for Admin UI
5. ⏱️ **Per-agent timeout config** - Different agents, different needs

### Nice-to-Have (Quality of Life)
6. 🛟 **Graceful degradation** - Resilience in multi-agent setups
7. 📚 **Better documentation** - Migration guide, examples, error handling
8. 🚀 **Caching, logging, metrics** - Production-ready features

---

## 📊 Overall Assessment

**Score**: 9/10 - Excellent foundation, minor gaps

**What's Great**:
- ✅ Unified MCP/A2A interface
- ✅ Type safety with Pydantic
- ✅ Webhook handling built-in
- ✅ Multi-agent support
- ✅ Clean API design

**What's Missing**:
- ⚠️ Custom auth headers (critical)
- 🔧 URL fallback handling (important)
- 📚 Production docs (migration guide, error handling)

**Recommendation**: With custom auth header support added, this library is production-ready and solves real problems. We're excited to adopt it!

---

## 🤝 Offer to Collaborate

We're happy to:
- Contribute PRs for requested features
- Provide real-world testing and feedback
- Share production usage patterns
- Help improve documentation

**Contact**: maintainers@adcontextprotocol.org (or open GitHub issues)

Thank you for building this library! It solves real problems we face daily.
