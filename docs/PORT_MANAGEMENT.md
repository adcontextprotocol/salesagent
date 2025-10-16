# Port Management System

## Overview

This document describes the centralized port configuration system that solves port conflict issues across test environments.

## Problem Statement

Before this system, we had:
- Hardcoded ports scattered across files (5433, 5435, 8092, etc.)
- Conductor workspace-specific ports conflicting with CI
- Docker Compose using different ports than tests
- Configuration drift causing flaky tests and port conflicts

## Solution: scripts/test_ports.py

A single Python module that manages all test port allocations with environment detection.

## Quick Start

```python
from scripts.test_ports import get_ports

# Auto-detect environment
ports = get_ports()  # Returns {postgres: 5433, mcp: 8092, a2a: 8094, admin: 8093}

# Explicit mode
ports = get_ports(mode="ci")     # GitHub Actions ports
ports = get_ports(mode="e2e")    # Docker Compose ports
ports = get_ports(mode="local")  # Conductor workspace ports
ports = get_ports(mode="auto")   # Auto-detect (default)

# Use ports
postgres_port = ports["postgres"]
db_url = f"postgresql://...@localhost:{postgres_port}/..."
```

## Port Modes

### CI Mode (GitHub Actions)
- **When**: Running in GitHub Actions or CI environment
- **Detection**: `GITHUB_ACTIONS=true` or `CI=true`
- **Ports**:
  - postgres: 5433 (integration tests container)
  - mcp: 8092 (E2E MCP server)
  - a2a: 8094 (E2E A2A server)
  - admin: 8093 (E2E Admin UI)

### E2E Mode (Docker Compose)
- **When**: E2E tests with full Docker Compose stack
- **Ports**:
  - postgres: 5435 (inside docker-compose, separate from integration tests)
  - mcp: 8092 (maps to container port 8080)
  - a2a: 8094 (maps to container port 8091)
  - admin: 8093 (maps to container port 8001)

### Local Mode (Conductor Workspace)
- **When**: Working in Conductor workspace
- **Detection**: `CONDUCTOR_POSTGRES_PORT` environment variable
- **Ports**: Read from `.env` file (unique per workspace)
  - Example: postgres: 5496, mcp: 8144, a2a: 8155, admin: 8165

### Auto Mode (Default)
- Detects CI → uses CI ports
- Detects Conductor → uses local ports
- Otherwise → uses CI ports (safe default)

## Usage Examples

### In Test Files

```python
# tests/integration/conftest.py
from scripts.test_ports import get_ports

ports = get_ports(mode="auto")
postgres_port = ports["postgres"]
conn_params = {
    "host": "localhost",
    "port": postgres_port,
    "user": "adcp_user",
    "password": "test_password"
}
```

### In Shell Scripts

```bash
# run_all_tests.sh
POSTGRES_PORT=$(uv run python -c "from scripts.test_ports import get_ports; print(get_ports(mode='ci')['postgres'])")
docker run -p ${POSTGRES_PORT}:5432 postgres:15
```

### CLI Usage

```bash
# Check port configuration
python scripts/test_ports.py ci
# Output:
# Port Configuration (mode=ci):
#   postgres   5433  ✓
#   mcp        8092  ✓
#   a2a        8094  ✓
#   admin      8093  ✓
# Database URL: postgresql://adcp_user:test_password@localhost:5433/adcp_test
# ✅ Port configuration valid

# Check if ports are available
python scripts/test_ports.py local
# Shows ✓ or ✗ (in use) for each port
```

## Port Validation

```python
from scripts.test_ports import validate_ports, get_ports

ports = get_ports(mode="ci")
errors = validate_ports(ports, check_availability=True)
if errors:
    print("Port configuration issues:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
```

Validates:
- No port conflicts (same port for multiple services)
- Ports in valid range (1024-65535)
- Port availability (optional)

## Helper Functions

### get_database_url()

```python
from scripts.test_ports import get_database_url

# Get PostgreSQL URL with correct port
db_url = get_database_url(mode="ci", db_name="adcp_test")
# postgresql://adcp_user:test_password@localhost:5433/adcp_test
```

### is_ci_mode()

```python
from scripts.test_ports import is_ci_mode

if is_ci_mode():
    print("Running in CI environment")
```

### is_port_available()

```python
from scripts.test_ports import is_port_available

if is_port_available(5433):
    print("Port 5433 is free")
else:
    print("Port 5433 is in use")
```

## Migration Guide

### Before (Hardcoded Ports)

```python
# ❌ BAD - Hardcoded port
conn_params = {
    "host": "localhost",
    "port": 5433,  # What if this conflicts with Conductor workspace?
    "user": "adcp_user"
}
```

### After (Centralized Configuration)

```python
# ✅ GOOD - Use centralized ports
from scripts.test_ports import get_ports

ports = get_ports()
conn_params = {
    "host": "localhost",
    "port": ports["postgres"],  # Works in CI, local, and Conductor
    "user": "adcp_user"
}
```

## Environment Variable Priority

1. **Explicit TEST_* variables** (highest priority):
   - `TEST_POSTGRES_PORT`, `TEST_MCP_PORT`, etc.
2. **Mode-specific behavior**:
   - CI mode → fixed CI ports
   - E2E mode → fixed E2E ports
   - Local mode → CONDUCTOR_* or fallback env vars
3. **Fallback** (lowest priority):
   - CI ports (safe defaults)

## Testing the System

```bash
# Test all modes
python scripts/test_ports.py ci
python scripts/test_ports.py e2e
python scripts/test_ports.py local
python scripts/test_ports.py auto

# Run unit tests (if any)
pytest tests/unit/test_test_ports.py -v
```

## Troubleshooting

### Port Conflicts

**Symptom**: "Port 5433 is already in use"

**Solution**:
1. Check what's using the port:
   ```bash
   lsof -i :5433
   ```
2. Stop conflicting service or use different port:
   ```bash
   # Override with environment variable
   export TEST_POSTGRES_PORT=5434
   ```

### Wrong Ports Detected

**Symptom**: Tests using wrong ports in Conductor workspace

**Solution**:
1. Verify .env file has CONDUCTOR_* variables:
   ```bash
   cat .env | grep CONDUCTOR_POSTGRES_PORT
   ```
2. Force local mode:
   ```python
   ports = get_ports(mode="local")
   ```

### CI Tests Failing with Port Issues

**Symptom**: CI tests fail but local tests pass

**Solution**:
1. Run tests in CI mode locally:
   ```bash
   ./run_all_tests.sh ci
   ```
2. Check that run_all_tests.sh uses `get_ports(mode="ci")`

## Files Modified

- ✅ `scripts/test_ports.py` - Central port configuration module
- ✅ `run_all_tests.sh` - Uses centralized ports for CI mode
- ✅ `tests/integration/conftest.py` - Integration tests use auto-detection
- ✅ `tests/e2e/conftest.py` - E2E tests use e2e mode
- ✅ `CLAUDE.md` - Documentation updated

## Best Practices

1. **Never hardcode ports** in test files
2. **Use auto mode** unless you need specific behavior
3. **Validate ports** before running tests in scripts
4. **Document overrides** if using TEST_* environment variables
5. **Test in CI mode** locally before pushing

## Future Enhancements

Potential improvements:
- [ ] Add port reservation system (lock files)
- [ ] Support for port ranges (find next available)
- [ ] Integration with docker-compose.yml generation
- [ ] Pre-commit hook to check for hardcoded ports
- [ ] Port conflict resolution (auto-increment)

## References

- Implementation: `scripts/test_ports.py`
- Documentation: `CLAUDE.md` (Centralized Port Configuration System section)
- Test script: `run_all_tests.sh`
- Integration tests: `tests/integration/conftest.py`
- E2E tests: `tests/e2e/conftest.py`
