# 🧪 AdCP Testing Guide

This guide explains the different types of testing available in the AdCP Sales Agent project.

## 📋 Testing Overview

| Type | Purpose | When to Use | Location |
|------|---------|-------------|----------|
| **E2E Tests** | Automated protocol validation | CI/CD, regression testing | `tests/e2e/` |
| **Simulations** | Developer tools & demos | Manual testing, debugging | `tools/simulations/` |
| **Unit Tests** | Individual component testing | Development, fast feedback | `tests/unit/` |
| **Integration Tests** | Database & service integration | Database changes, API testing | `tests/integration/` |

## 🚀 Quick Start

### For Developers (Manual Testing)
```bash
# 1. Start services
docker-compose up -d

# 2. Run debug simulation to see protocol in action
uv run python tools/simulations/debug_e2e.py

# 3. Run debug with options
uv run python tools/simulations/debug_e2e.py --verbose              # Full stack traces
uv run python tools/simulations/debug_e2e.py --skip-a2a             # MCP only
uv run python tools/simulations/debug_e2e.py --server-url http://remote:8166  # External server

# 4. Run full business scenario simulation
uv run python tools/simulations/run_simulation.py
```

### For CI/CD (Automated Testing)
```bash
# Run all E2E tests (comprehensive protocol validation)
uv run pytest tests/e2e/ -v

# Run specific E2E test
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_product_discovery -v
```

## 🔍 E2E Tests vs Simulations

### **E2E Tests** (`tests/e2e/`)
- **Purpose**: Automated validation that the AdCP protocol implementation is correct
- **Characteristics**:
  - ✅ **Pytest framework** with fixtures and assertions
  - ✅ **Protocol compliance** - validates every field against AdCP spec
  - ✅ **Multiple modes** - can run against any AdCP-compliant server
  - ✅ **Testing hooks** - uses X-Dry-Run, X-Mock-Time, X-Test-Session-ID
  - ✅ **CI/CD integration** - runs on PRs and main branch (catch issues early!)
  - ✅ **Comprehensive assertions** - catches regressions and spec violations
- **Example**: Validates that `get_products` returns required fields with correct data types

### **Simulations** (`tools/simulations/`)
- **Purpose**: Developer tools for manual testing and business scenario demos
- **Characteristics**:
  - 🎨 **Rich console output** - visual feedback with colors and tables
  - 🏢 **Business scenarios** - realistic campaigns (Purina pet food, Acme Corp)
  - ⏰ **Timeline progression** - shows campaign lifecycle over time
  - 🧪 **Educational** - demonstrates real-world usage patterns
  - 🔧 **Debugging** - shows exactly what APIs would be called in production
  - 🎯 **Interactive** - can be run manually to explore functionality
- **Example**: Shows a complete campaign from planning → buying → creatives → delivery

## 📂 Directory Structure

```
tests/
├── e2e/                           # End-to-end protocol tests
│   ├── test_adcp_full_lifecycle.py   # Main E2E test suite
│   └── conftest.py                   # Test fixtures
├── integration/                   # Database & service integration
├── unit/                         # Fast unit tests
└── smoke/                        # Quick smoke tests

tools/
├── simulations/                  # Developer simulation tools
│   ├── debug_e2e.py                # Debug with request/response logging
│   ├── run_simulation.py           # Automated simulation runner
│   └── simulation_full.py          # Full business lifecycle demo
└── demos/                        # Feature-specific demos

docs/
└── testing/                     # Testing documentation
    ├── README.md                   # This file
    ├── TEST_DEBUGGING_GUIDE.md     # Detailed debugging guide
    └── README_E2E_TESTING.md       # E2E testing specifics
```

## 🔧 Development Workflow

### 1. **Making Changes**
- Write/modify code
- Run relevant unit tests: `uv run pytest tests/unit/ -k "your_feature"`
- Test manually with simulations: `uv run python tools/simulations/debug_e2e.py`

### 2. **Before Committing**
- Run E2E tests: `uv run pytest tests/e2e/ -v`
- Ensure no regressions in protocol behavior
- Check that both MCP and A2A protocols work

### 3. **For New Features**
- Add unit tests for new functions/classes
- Add E2E test scenarios if they affect the AdCP protocol
- Create simulation demos if they showcase new capabilities

## 🐳 Docker Services

All testing requires the following services:
```yaml
# Started with: docker-compose up -d
services:
  postgres: 5518      # Database
  adcp-server: 8166   # MCP server (AdCP protocol)
  a2a-server: 8091    # A2A server (natural language)
  admin-ui: 8087      # Admin interface
```

**Health Checks**: All services have health endpoints and startup validation.

## 🧪 Testing Hooks (AdCP Spec)

The E2E tests implement [testing hooks from the AdCP specification](https://github.com/adcontextprotocol/adcp/pull/34):

| Hook | Purpose | Usage |
|------|---------|--------|
| `X-Dry-Run: true` | Validate without executing | Test requests without side effects |
| `X-Mock-Time: 2025-08-15T10:00:00Z` | Control time | Deterministic date progression |
| `X-Test-Session-ID: uuid` | Isolate test runs | Parallel test execution |
| `X-Jump-To-Event: campaign_start` | Skip to events | Test specific campaign phases |

## 📊 Test Results & Coverage

### E2E Test Coverage
- ✅ **Core Protocol**: `get_products`, `create_media_buy`, `add_creative_assets`, `get_delivery`
- ✅ **Both Protocols**: MCP (structured) and A2A (natural language)
- ✅ **Field Validation**: Every required field validated against spec
- ✅ **Error Handling**: Invalid inputs, missing data, malformed requests
- ✅ **Business Logic**: Budget limits, date validation, targeting rules

### Future Work (GitHub Issues)
- **#89**: Creative Format Management E2E
- **#90**: Advanced Targeting Capabilities E2E
- **#91**: Multi-Tenant Isolation E2E
- **#92**: Performance Optimization Features E2E
- **#93**: Error Handling & Recovery E2E
- **#94**: Manual Approval Workflows E2E
- **#95**: Bulk Operations E2E
- **#96**: Performance & Scale Testing E2E

## 🛠️ Troubleshooting

### Common Issues

**"Connection refused"**
- Ensure Docker services are running: `docker-compose ps`
- Check health endpoints: `curl http://localhost:8166/health`

**"Authentication failed"**
- Token generation requires running Docker container
- Debug script will auto-generate valid tokens

**"Tests skipping"**
- E2E tests run on PRs and main branch (changed from main-only)
- Check pytest markers: tests with `@pytest.mark.skip_ci` are skipped in CI

**"Schema validation errors"**
- E2E tests validate against exact AdCP specification
- Check field names, data types, and required fields match the spec

### Debug Commands
```bash
# View service logs
docker-compose logs -f adcp-server

# Check service health
curl http://localhost:8166/health
curl http://localhost:8091/

# Run debug with verbose output
uv run python tools/simulations/debug_e2e.py

# Run E2E tests with debug output
uv run pytest tests/e2e/ -v -s --tb=short
```

## 📚 Learn More

- **[TEST_DEBUGGING_GUIDE.md](./TEST_DEBUGGING_GUIDE.md)** - Detailed debugging instructions
- **[README_E2E_TESTING.md](./README_E2E_TESTING.md)** - E2E testing specifics
- **AdCP Specification** - Protocol requirements and testing hooks
- **GitHub Issues #89-96** - Future testing improvements planned
