# AdCP Python Client Library Analysis

**Date**: 2025-11-05
**Package**: `adcp` v0.1.2
**PyPI**: https://pypi.org/project/adcp/
**GitHub**: https://github.com/adcontextprotocol/adcp-client-python

## Executive Summary

The `adcp` Python package is an official AdCP client library that provides a unified interface for calling both **MCP** and **A2A** protocol agents. It was published today (2025-11-05) and offers several compelling features that could simplify our current implementation.

**Recommendation**: ✅ **YES - Adopt for external agent calls (signals, creative agents)**

The library is well-suited for replacing our custom MCP client implementation when communicating with **external agents** (signals agents, creative agents). However, it should **not** replace our internal MCP server implementation.

---

## Package Overview

### Key Features

1. **Unified Protocol Support**
   - Supports both MCP and A2A protocols with same API
   - Auto-detects protocol type
   - Handles protocol differences transparently

2. **Distributed Operations Handling**
   - Built-in support for synchronous vs asynchronous completions
   - Webhook registration and management
   - Status change handlers
   - Operation ID tracking

3. **Type Safety**
   - Full Pydantic validation
   - Type hints with IDE autocomplete
   - Validated request/response models

4. **Multi-Agent Operations**
   - Parallel execution across multiple agents
   - Agent registry and configuration
   - Per-agent authentication

5. **Security**
   - Webhook signature verification (HMAC)
   - Built-in auth token management
   - Environment-based configuration

6. **Property Discovery** (AdCP v2.2.0)
   - Agent crawling for property discovery
   - Property index building
   - Tag-based agent lookup

### Dependencies

```
httpx>=0.24.0
pydantic>=2.0.0
typing-extensions>=4.5.0
a2a-sdk>=0.3.0
mcp>=0.9.0
```

**Compatibility**: ✅ All dependencies align with our current stack

---

## Current Implementation vs. AdCP Library

### Our Current Approach

**Custom MCP Client** (`src/core/utils/mcp_client.py`):
- 280 lines of custom code
- Built on `fastmcp.client.StreamableHttpTransport`
- Manual auth header building
- Custom retry logic with exponential backoff
- URL fallback handling (/mcp suffix)

**Usage Locations**:
1. **Signals Agent Registry** (`src/core/signals_agent_registry.py`)
   - Calls external signals agents for audience targeting
   - Uses `create_mcp_client()` for connections
   - ~100 lines of MCP-specific code

2. **Creative Agent Registry** (`src/core/creative_agent_registry.py`)
   - Calls external creative agents for format discovery
   - Uses `create_mcp_client()` for connections
   - ~200 lines of MCP-specific code

### What AdCP Library Provides

```python
# Instead of our custom client:
from src.core.utils.mcp_client import create_mcp_client

async with create_mcp_client(agent_url=url, auth=auth, auth_header=header) as client:
    result = await client.call_tool("get_signals", params)

# Use AdCP library:
from adcp import ADCPMultiAgentClient
from adcp.types import AgentConfig

client = ADCPMultiAgentClient(agents=[
    AgentConfig(id="signals_agent", agent_uri=url, protocol="mcp", auth_token=token)
])
result = await client.agent("signals_agent").get_signals(brief="query")
```

**Benefits**:
- ✅ Protocol abstraction (works with both MCP and A2A)
- ✅ Type-safe response models
- ✅ Built-in webhook handling
- ✅ Less custom code to maintain
- ✅ Official support from AdCP community

---

## Migration Assessment

### ✅ Should Migrate (External Agent Calls)

#### 1. **Signals Agent Registry**

**Current**: Custom MCP client in `src/core/signals_agent_registry.py`

**Migration Impact**: 🟢 **LOW RISK**

**Benefits**:
- Replace `create_mcp_client()` with `ADCPMultiAgentClient`
- Get type-safe `GetSignalsResponse` model
- Simplify connection retry logic
- Support both MCP and A2A signals agents

**Code Reduction**: ~30-40% fewer lines

**Compatibility**: ✅ Perfect fit - signals agents are external

#### 2. **Creative Agent Registry**

**Current**: Custom MCP client in `src/core/creative_agent_registry.py`

**Migration Impact**: 🟢 **LOW RISK**

**Benefits**:
- Replace `create_mcp_client()` with `ADCPMultiAgentClient`
- Get type-safe `ListCreativeFormatsResponse` model
- Support both MCP and A2A creative agents
- Built-in format caching via library

**Code Reduction**: ~40-50% fewer lines

**Compatibility**: ✅ Perfect fit - creative agents are external

#### 3. **Property Discovery** (New Feature)

**Current**: Not implemented

**Migration Impact**: 🟢 **NO RISK** (new feature)

**Benefits**:
- Use `PropertyCrawler` from `adcp.discovery`
- Build agent registries automatically
- Enable property-based agent lookup

**Added Value**: 🚀 New capability we don't have

---

### ❌ Should NOT Migrate (Internal Services)

#### 1. **Our MCP Server** (`src/core/main.py`)

**Current**: FastMCP server exposing our tools

**Recommendation**: ❌ **DO NOT MIGRATE**

**Reasons**:
- The `adcp` library is a **client**, not a server
- Our MCP server implementation is correct and working
- We use `@mcp.tool()` decorators for tool registration
- No benefit to changing this

#### 2. **Our A2A Server** (`src/a2a_server/`)

**Current**: python-a2a server implementation

**Recommendation**: ❌ **DO NOT MIGRATE**

**Reasons**:
- The `adcp` library is a **client**, not a server
- Our A2A server uses `python-a2a` library (standard)
- No replacement needed

---

## Migration Strategy

### Phase 1: Signals Agent Registry (Week 1)

**Goal**: Replace custom MCP client in signals agent calls

**Steps**:
1. Add `adcp` dependency to `pyproject.toml`
2. Create adapter wrapper for `SignalsAgentRegistry`:
   ```python
   from adcp import ADCPMultiAgentClient
   from adcp.types import AgentConfig

   class SignalsAgentRegistry:
       def __init__(self):
           self._client = None

       def _get_client(self, tenant_id: str) -> ADCPMultiAgentClient:
           """Build multi-agent client from database config."""
           agents = self._load_agents_from_db(tenant_id)
           agent_configs = [
               AgentConfig(
                   id=agent.id,
                   agent_uri=agent.agent_url,
                   protocol="mcp",  # or "a2a" if detected
                   auth_token=agent.auth_credentials
               )
               for agent in agents
           ]
           return ADCPMultiAgentClient(agents=agent_configs)
   ```

3. Update `_get_signals_from_agent()` to use `adcp` client
4. Remove custom `create_mcp_client()` calls
5. Test with Optable signals agent (real world validation)

**Testing**:
- ✅ Unit tests for adapter wrapper
- ✅ Integration tests with mock agents
- ✅ E2E test with real Optable agent

**Risk**: 🟢 LOW - Signals are non-critical for core functionality

---

### Phase 2: Creative Agent Registry (Week 2)

**Goal**: Replace custom MCP client in creative agent calls

**Steps**:
1. Create adapter wrapper for `CreativeAgentRegistry`
2. Migrate `list_creative_formats()` calls
3. Migrate `get_format()` calls
4. Update format caching to use library's cache
5. Test with AdCP standard creative agent

**Testing**:
- ✅ Unit tests for adapter wrapper
- ✅ Integration tests with mock creative agents
- ✅ E2E test with real creative agent

**Risk**: 🟢 LOW - Creative formats are cached, fallbacks exist

---

### Phase 3: Property Discovery (Week 3)

**Goal**: Enable property-based agent discovery

**Steps**:
1. Add `PropertyCrawler` integration
2. Build tenant property index on startup
3. Add Admin UI for property-based agent search
4. Enable property-tagged product discovery

**Testing**:
- ✅ Unit tests for property crawler
- ✅ Integration test for index building
- ✅ Admin UI test for property search

**Risk**: 🟢 LOW - New feature, no existing code to break

---

### Phase 4: Cleanup (Week 4)

**Goal**: Remove custom MCP client code

**Steps**:
1. Remove `src/core/utils/mcp_client.py` (if no other usage)
2. Update tests to use `adcp` fixtures
3. Update documentation
4. Remove unused imports

**Testing**:
- ✅ Full regression test suite
- ✅ E2E test with real external agents

**Risk**: 🟡 MEDIUM - Need to verify no hidden dependencies

---

## Code Comparison Examples

### Before (Custom MCP Client)

```python
# src/core/signals_agent_registry.py
from src.core.utils.mcp_client import create_mcp_client

async def _get_signals_from_agent(self, agent, brief, tenant_id):
    try:
        async with create_mcp_client(
            agent_url=agent.agent_url,
            auth=agent.auth,
            auth_header=agent.auth_header,
            timeout=agent.timeout,
            max_retries=3,
        ) as client:
            params = {"brief": brief, "tenant_id": tenant_id}
            result = await client.call_tool("get_signals", params)

            # Parse result (manual)
            if hasattr(result, "structured_content"):
                signals_data = result.structured_content
            else:
                # Fallback parsing...
                signals_data = json.loads(result.content[0].text)

            return signals_data.get("signals", [])
    except Exception as e:
        logger.error(f"Failed: {e}")
        raise
```

### After (AdCP Library)

```python
# src/core/signals_agent_registry.py
from adcp import ADCPMultiAgentClient
from adcp.types import AgentConfig

async def _get_signals_from_agent(self, agent, brief, tenant_id):
    # Build client config
    client = ADCPMultiAgentClient(agents=[
        AgentConfig(
            id=agent.id,
            agent_uri=agent.agent_url,
            protocol="mcp",
            auth_token=agent.auth_credentials,
            auth_header=agent.auth_header,
        )
    ])

    # Type-safe call
    result = await client.agent(agent.id).get_signals(
        brief=brief,
        tenant_id=tenant_id
    )

    # Type-safe response (GetSignalsResponse)
    if result.status == "completed":
        return result.data.signals  # Full type hints!
    else:
        # Handle async completion
        logger.info(f"Async: webhook at {result.submitted.webhook_url}")
        return []
```

**Differences**:
- ✅ No manual JSON parsing
- ✅ Type-safe response models
- ✅ Built-in async/webhook handling
- ✅ Cleaner error handling
- ✅ 30% fewer lines

---

## Benefits Summary

### Code Quality
- ✅ **Less custom code** - Reduce maintenance burden
- ✅ **Type safety** - Full Pydantic validation
- ✅ **Protocol agnostic** - Support both MCP and A2A
- ✅ **Better testing** - Standard library fixtures

### Features
- ✅ **Webhook handling** - Built-in async operation support
- ✅ **Property discovery** - New capability we don't have
- ✅ **Multi-agent** - Parallel execution across agents
- ✅ **Security** - HMAC signature verification

### Maintenance
- ✅ **Official support** - AdCP community maintained
- ✅ **Documentation** - Better docs than our custom code
- ✅ **Updates** - Get protocol updates automatically
- ✅ **Bug fixes** - Community-driven fixes

---

## Risks and Mitigations

### Risk 1: Library Maturity
**Risk**: v0.1.2 is early stage, may have bugs
**Severity**: 🟡 MEDIUM
**Mitigation**:
- Start with non-critical paths (signals agents)
- Keep fallback to custom client during migration
- Report issues to AdCP maintainers
- Contribute fixes back to library

### Risk 2: Breaking Changes
**Risk**: Library API may change between versions
**Severity**: 🟢 LOW
**Mitigation**:
- Pin exact version in pyproject.toml
- Review changelogs before upgrading
- Maintain adapter layer for easy rollback
- Keep comprehensive test coverage

### Risk 3: Feature Gaps
**Risk**: Library may not support all our use cases
**Severity**: 🟢 LOW
**Mitigation**:
- Audit all current MCP client usage first
- Test edge cases during Phase 1
- Keep custom client for unsupported features
- Contribute missing features to library

### Risk 4: Performance
**Risk**: Library may be slower than custom client
**Severity**: 🟢 LOW
**Mitigation**:
- Benchmark against current implementation
- Profile hot paths
- Use library's caching features
- Optimize if needed (or contribute back)

---

## Cost-Benefit Analysis

### Costs
- **Migration Time**: ~4 weeks (phased approach)
- **Testing Effort**: Medium (comprehensive test suite needed)
- **Learning Curve**: Low (similar API to our custom client)
- **Risk**: Low (external agents are non-critical)

### Benefits
- **Code Reduction**: ~200-300 lines removed
- **Maintenance**: 30% less custom code to maintain
- **Features**: Property discovery, webhook handling
- **Type Safety**: Full Pydantic validation
- **Community**: Official AdCP support

**ROI**: ✅ **POSITIVE** - Benefits outweigh costs

---

## Recommendation

### ✅ Adopt for External Agent Calls

**Rationale**:
1. The library solves problems we've already solved (but better)
2. It's officially supported by the AdCP community
3. It provides features we don't have (property discovery, webhooks)
4. It reduces our maintenance burden
5. It's protocol-agnostic (future-proofs us for A2A signals agents)

### 📋 Action Items

**Immediate** (This Week):
1. ✅ Add `adcp==0.1.2` to `pyproject.toml`
2. ✅ Create spike branch for Phase 1 migration
3. ✅ Test with Optable signals agent

**Short Term** (Month 1):
1. ✅ Complete Phase 1: Signals Agent Registry
2. ✅ Complete Phase 2: Creative Agent Registry
3. ✅ Document migration patterns

**Medium Term** (Month 2):
1. ✅ Complete Phase 3: Property Discovery
2. ✅ Complete Phase 4: Cleanup
3. ✅ Contribute improvements to library

### ❌ Do NOT Replace

**Internal Services** (keep as-is):
- ❌ Our MCP server (`src/core/main.py`)
- ❌ Our A2A server (`src/a2a_server/`)
- ❌ Tool implementations (shared `_impl` functions)

These are **server** implementations, not **client** calls. The `adcp` library is a client, not a server framework.

---

## Conclusion

The `adcp` Python library is a **strong fit** for our external agent communication needs. It provides a well-designed, type-safe, protocol-agnostic client that aligns with our architecture and reduces maintenance burden.

**Recommendation**: ✅ **Proceed with phased migration**

Start with signals agents (lowest risk, highest learning value), then expand to creative agents, and finally add property discovery as a new capability.

The migration is low-risk, high-value, and positions us well for future AdCP protocol evolution.
