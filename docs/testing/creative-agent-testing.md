# Creative Agent Integration Testing

## Overview

This codebase includes two types of creative validation tests:

1. **Mocked Tests** (`test_creative_validation_failures.py`)
   - Mock the creative agent responses
   - Test validation logic and error handling
   - Fast, run without external dependencies
   - Good for CI/CD pipelines

2. **Real Integration Tests** (`test_creative_agent_integration.py`)
   - Use the actual creative agent via MCP
   - Test full integration path
   - Require creative agent service running
   - More comprehensive, slower

## Setup

### Add Creative Agent to Docker Compose

The creative agent is now included in `docker-compose.yml`:

```yaml
services:
  creative-agent:
    image: ghcr.io/adcontextprotocol/creative-agent:latest
    ports:
      - "${CREATIVE_AGENT_PORT:-8095}:8080"
```

### Start Creative Agent

```bash
# Start just the creative agent
docker-compose up creative-agent

# Or start everything
docker-compose up
```

The creative agent will be available at:
- **URL**: `http://localhost:8095`
- **MCP Endpoint**: `http://localhost:8095/mcp`
- **Health Check**: `http://localhost:8095/health`

## Running Tests

### Mocked Tests (Default)

These run without the creative agent:

```bash
# Run mocked validation tests
pytest tests/integration/test_creative_validation_failures.py -v

# These tests verify:
# - Empty preview_result rejection
# - Network error handling
# - AdCP response schema compliance
```

### Real Integration Tests

These require the creative agent running:

```bash
# 1. Start creative agent
docker-compose up -d creative-agent

# 2. Run integration tests
CREATIVE_AGENT_URL=http://localhost:8095 \
pytest tests/integration/test_creative_agent_integration.py -v

# These tests verify:
# - Full MCP call path
# - Real preview generation
# - Actual creative agent validation
```

### Full Test Suite

Run ALL tests with creative agent:

```bash
# Start services
docker-compose up -d postgres creative-agent

# Run all tests
./run_all_tests.sh ci
```

## Test Scenarios

### Mocked Tests (test_creative_validation_failures.py)

| Test | Purpose | Creative Agent State |
|------|---------|----------------------|
| `test_empty_preview_result_rejects_creative` | Preview returns empty dict | Mocked |
| `test_preview_none_rejects_creative` | Preview returns None | Mocked |
| `test_network_error_rejects_creative_with_retry_message` | Network error simulation | Mocked |
| `test_update_with_empty_preview_rejects` | Update with invalid preview | Mocked |
| `test_valid_preview_accepts_creative` | Valid preview acceptance | Mocked |

### Real Integration Tests (test_creative_agent_integration.py)

| Test | Purpose | Creative Agent State |
|------|---------|----------------------|
| `test_valid_creative_with_real_agent` | End-to-end valid creative | Running |
| `test_invalid_creative_rejected_by_agent` | Agent validation failure | Running |
| `test_creative_agent_unavailable` | Network error (manual) | Stopped |
| `test_list_formats_from_agent` | Format discovery | Running |
| `test_preview_creative_with_valid_format` | Direct MCP call | Running |

## Manual Testing Scenarios

### Test Network Failure Handling

```bash
# 1. Start creative agent
docker-compose up -d creative-agent

# 2. In another terminal, run test that will fail
pytest tests/integration/test_creative_agent_integration.py::TestCreativeAgentIntegration::test_valid_creative_with_real_agent -v

# 3. While test is running, stop creative agent
docker-compose stop creative-agent

# 4. Verify error handling and retry messaging
```

### Test Creative Validation

```bash
# Test with various creative formats
pytest tests/integration/test_creative_agent_integration.py::TestCreativeAgentIntegration::test_invalid_creative_rejected_by_agent -v

# Check logs
docker-compose logs creative-agent
```

## Troubleshooting

### Creative Agent Not Starting

```bash
# Check if port is in use
lsof -i :8095

# Check logs
docker-compose logs creative-agent

# Try different port
CREATIVE_AGENT_PORT=8096 docker-compose up creative-agent
```

### Tests Failing

```bash
# Verify creative agent is healthy
curl http://localhost:8095/health

# Check MCP endpoint
curl -X POST http://localhost:8095/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Restart creative agent
docker-compose restart creative-agent
```

### Wrong Creative Agent Version

```bash
# Pull latest image
docker pull ghcr.io/adcontextprotocol/creative-agent:latest

# Restart with fresh image
docker-compose down creative-agent
docker-compose up -d creative-agent
```

## CI/CD Integration

### GitHub Actions

The CI pipeline runs mocked tests by default (fast, no external dependencies).

To enable real creative agent tests in CI:

```yaml
# .github/workflows/test.yml
services:
  creative-agent:
    image: ghcr.io/adcontextprotocol/creative-agent:latest
    ports:
      - 8095:8080

env:
  CREATIVE_AGENT_URL: http://localhost:8095
```

### Pre-Push Hook

The pre-push hook runs mocked tests only (fast validation).

For full validation including real creative agent:

```bash
# Start services
docker-compose up -d postgres creative-agent

# Run full suite
./run_all_tests.sh ci
```

## Architecture

### Mocked Tests Architecture

```
Test → _sync_creatives_impl() → [Mocked CreativeAgentRegistry] → [Simulated Response]
                                          ↓
                                    Validation Logic
                                          ↓
                                    Database / Response
```

### Real Integration Tests Architecture

```
Test → _sync_creatives_impl() → CreativeAgentRegistry → MCP Client → Creative Agent
                                          ↓                               ↓
                                    Validation Logic              preview_creative
                                          ↓                               ↓
                                    Database / Response ← ← ← ← ← ← Preview URL
```

## Best Practices

1. **Use mocked tests for**:
   - Unit testing validation logic
   - CI/CD pipelines (fast feedback)
   - Testing error handling edge cases

2. **Use real integration tests for**:
   - Verifying MCP protocol implementation
   - Testing actual creative agent compatibility
   - Pre-release validation
   - Debugging integration issues

3. **Always run both**:
   - Before merging to main
   - When changing creative validation code
   - When updating creative agent version

## References

- Creative Agent Repo: https://github.com/adcontextprotocol/creative-agent
- AdCP Spec: https://adcontextprotocol.org/docs/
- MCP Protocol: https://github.com/anthropics/mcp
