# Add Agent2Agent (A2A) Protocol Support

## Summary

This PR adds support for Google's Agent2Agent (A2A) protocol alongside the existing MCP implementation, enabling the AdCP Sales Agent to communicate with AI agents using either protocol. Both protocols share the same underlying business logic through a new TaskExecutor architecture.

## Key Changes

### 1. Dual Protocol Architecture
- **TaskExecutor** (`task_executor.py`): Core business logic extracted from MCP implementation
- **MCP Facade** (`mcp_facade.py`): Thin adapter for MCP protocol  
- **A2A Facade** (`a2a_facade.py`): Thin adapter for A2A protocol
- **Shared Context Management** (`context_manager.py`): Conversation persistence for both protocols

### 2. A2A Protocol Implementation
- Full JSON-RPC 2.0 support at `/rpc` endpoint
- Agent Card at `/.well-known/agent-card.json`
- Structured data responses with both text and data parts
- Task-based response format for all operations
- Special handling for `message/send` with intelligent responses

### 3. Production Deployment
- A2A server runs on port 8090
- Updated `debug_start.sh` to start A2A server
- Updated `fly-proxy.py` to route A2A requests 
- Successfully deployed and tested on fly.dev

### 4. Testing
- Comprehensive A2A protocol tests (`test_a2a_unit.py`, `test_a2a_structured_data.py`)
- Consolidated protocol tests in `tests/protocol/` directory
- Verified structured data responses match AdCP specification
- Production deployment tested and confirmed working

### 5. Documentation
- Updated README with A2A protocol usage examples
- Added A2A implementation guidelines to CLAUDE.md
- Created ADCP_SPEC_ISSUES.md documenting specification ambiguities

## Files Changed

### Core Implementation
- `task_executor.py` - NEW: Shared business logic for both protocols
- `a2a_facade.py` - NEW: A2A protocol adapter
- `mcp_facade.py` - NEW: Refactored MCP as thin facade
- `context_manager.py` - NEW: Conversation state management
- `start_a2a.py` - NEW: A2A server launcher

### Database
- `alembic/versions/013_add_context_persistence.py` - NEW: Migration for context tables
- `models.py` - MODIFIED: Added context-related models
- `db_config.py` - MODIFIED: Improved connection handling

### Deployment
- `debug_start.sh` - MODIFIED: Start A2A server
- `fly-proxy.py` - MODIFIED: Route A2A requests
- `docker-compose.yml` - MODIFIED: Added A2A service

### Documentation
- `README.md` - MODIFIED: Added A2A protocol documentation and authentication guide
- `CLAUDE.md` - MODIFIED: Added implementation guidelines
- `docs/authentication.md` - NEW: Comprehensive authentication documentation

### Testing
- `test_a2a_unit.py` - NEW: A2A unit tests
- `test_a2a_structured_data.py` - NEW: Structured data validation
- `tests/protocol/test_a2a_protocol.py` - NEW: Consolidated protocol tests

## Breaking Changes

None. The existing MCP implementation continues to work unchanged.

## Testing

### Local Testing
```bash
# Run A2A protocol tests
uv run pytest test_a2a_unit.py -v
uv run python test_a2a_structured_data.py

# Test with A2A Inspector
npx @google/a2a-inspector http://localhost:8090
```

### Production Testing
✅ Deployed to fly.dev and verified:
- Agent Card accessible: https://adcp-sales-agent.fly.dev/.well-known/agent-card.json
- A2A RPC endpoint working: https://adcp-sales-agent.fly.dev/a2a/rpc
- Structured data responses verified

## Security & Authentication

### Authentication Implementation
- Token-based authentication for both MCP and A2A protocols
- Validates tokens against `principals` and `tenants` tables
- Multi-tenant isolation with proper access control
- All unauthorized requests properly rejected with error codes
- Audit logging of all authenticated operations

### Security Fixes
- Fixed SQL injection vulnerability in `context_manager.py` by using static SQL queries
- Improved error handling to avoid exposing sensitive information
- Added proper connection cleanup in error paths
- Tokens are never logged or exposed in error messages

### Authentication Testing
✅ Verified locally:
- Requests without auth headers are rejected
- Invalid tokens are rejected  
- Valid tokens grant appropriate access
- Tenant routing works correctly
- All operations are audit logged with principal_id

## Known Issues

The following spec ambiguities were discovered during implementation (documented in ADCP_SPEC_ISSUES.md):
1. Optional vs required product fields unclear
2. Price guidance structure for unavailable pricing
3. When structured data parts are required in message responses
4. Core vs optional targeting capabilities

## Next Steps

1. File spec clarification issues in AdCP repository
2. Add more comprehensive integration tests
3. Implement connection pooling for better performance
4. Add rate limiting for expensive operations

## Checklist

- [x] Code follows project conventions
- [x] Tests pass locally
- [x] Production deployment verified
- [x] Documentation updated
- [x] Security vulnerabilities addressed
- [x] No unnecessary files included