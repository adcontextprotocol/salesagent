# Testing Guide

## Overview

The AdCP Sales Agent test suite provides comprehensive testing infrastructure including:
- **Unified test runner** for all test categories
- **GitHub Actions** for CI/CD
- **Pre-push hooks** for local quality assurance
- **Coverage reporting** to track test completeness
- **Test authentication mode** for UI testing without OAuth

Tests are managed using `pytest` with `uv` for dependency management.

## Quick Start

### Initial Setup

```bash
# Install Git hooks (required for each workspace/worktree)
./setup_hooks.sh

# Run all tests
./run_all_tests.sh
```

**Note for Conductor users**: Git hooks are per-worktree, so you need to run `setup_hooks.sh` in each workspace. The `setup_conductor_workspace.sh` script does this automatically.

### Running Tests

The unified test runner (`run_all_tests.sh`) supports multiple modes:

```bash
# Standard test run (default)
./run_all_tests.sh

# Quick check (minimal output)
./run_all_tests.sh quick

# Verbose mode (see all output)
./run_all_tests.sh verbose

# Coverage report
./run_all_tests.sh coverage

# CI mode (for GitHub Actions)
./run_all_tests.sh ci
```

### Using the Python Test Runner

```bash
# Run all tests
uv run python scripts/run_tests.py all

# Run specific category
uv run python scripts/run_tests.py unit
uv run python scripts/run_tests.py integration
uv run python scripts/run_tests.py e2e

# With coverage
uv run python scripts/run_tests.py all --coverage

# List available categories
uv run python scripts/run_tests.py --list
```

## Test Categories

### 1. Unit Tests (`tests/unit/`)
**Purpose**: Test individual components in isolation  
**Runtime**: < 1 second per test  
**Dependencies**: None (all external dependencies mocked)  

**Key test files**:
- `test_schemas.py` - Data model validation
- `test_targeting.py` - Targeting system tests
- `test_creative_parsing.py` - Creative format parsing
- `test_auth.py` - Authentication logic
- `adapters/test_base.py` - Adapter interface compliance

### 2. Integration Tests (`tests/integration/`)
**Purpose**: Test component interactions with real services  
**Runtime**: < 5 seconds per test  
**Dependencies**: Database (SQLite/PostgreSQL), mocked external APIs  

**Key test files**:
- `test_main.py` - MCP server functionality
- `test_admin_ui.py` - Admin interface integration
- `test_creative_approval.py` - Creative workflow
- `test_human_tasks.py` - Human-in-the-loop tasks
- `test_ai_products.py` - AI product features
- `test_policy.py` - Policy compliance

### 3. End-to-End Tests (`tests/e2e/`)
**Purpose**: Test complete user workflows  
**Runtime**: < 30 seconds per test  
**Dependencies**: Full system stack, may use real external services  

**Key test files**:
- `test_full_campaign.py` - Complete campaign lifecycle
- `test_multi_tenant.py` - Multi-tenant scenarios
- `test_gam_integration.py` - Real GAM adapter integration

### 4. UI Tests (`tests/ui/`)
**Purpose**: Test web interface functionality  
**Dependencies**: Flask test client, test authentication mode  

**Key test files**:
- `test_auth_mode.py` - Test authentication mode
- `test_gam_viewer.py` - GAM line item viewer
- `test_parsing_ui.py` - Creative parsing UI

## Test Organization Structure

```
tests/
├── conftest.py                # Shared pytest fixtures
├── unit/                      # Fast, isolated unit tests
│   ├── adapters/             # Adapter-specific tests
│   ├── test_schemas.py       # Data model tests
│   ├── test_targeting.py     # Targeting system tests
│   └── test_auth.py          # Authentication tests
├── integration/              # Tests requiring database/services
│   ├── test_main.py         # MCP server integration
│   ├── test_admin_ui.py     # Admin UI integration
│   └── test_ai_products.py  # AI product features
├── e2e/                      # End-to-end tests
│   └── test_gam_integration.py # Real GAM integration
├── ui/                       # UI-specific tests
│   └── test_auth_mode.py    # Test authentication mode
└── fixtures/                 # Test data and builders
    ├── factories.py         # Factory classes
    └── data/               # Sample data files
```

## Running Tests with Different Databases

### SQLite (Default)
```bash
# Uses in-memory SQLite by default
uv run pytest tests/integration/
```

### PostgreSQL
```bash
# Start PostgreSQL container
docker-compose up -d postgres

# Run tests with PostgreSQL
DATABASE_URL=postgresql://adcp_user:password@localhost:5432/adcp_test \
  uv run pytest tests/integration/
```

## Test Markers

Tests use pytest markers for categorization:

```python
@pytest.mark.unit           # Unit tests
@pytest.mark.integration    # Integration tests
@pytest.mark.e2e           # End-to-end tests
@pytest.mark.slow          # Tests > 5 seconds
@pytest.mark.requires_db   # Needs database
@pytest.mark.requires_server # Needs running server
@pytest.mark.ai            # AI feature tests
@pytest.mark.skip_ci       # Skip in CI pipeline
```

Run tests by marker:
```bash
# Run only unit tests
uv run pytest -m unit

# Skip slow tests
uv run pytest -m "not slow"

# Run AI tests
uv run pytest -m ai
```

## UI Test Authentication Mode

The system includes a test authentication mode for automated UI testing without OAuth.

### Setup

1. **Enable test mode** (development only):
   ```bash
   export ADCP_AUTH_TEST_MODE=true
   ```

2. **Customize test credentials** (optional):
   ```bash
   export TEST_SUPER_ADMIN_EMAIL=test@example.com
   export TEST_SUPER_ADMIN_PASSWORD=secure_test_pass
   ```

3. **Start services with test mode**:
   ```bash
   # Copy override file
   cp docker-compose.override.example.yml docker-compose.override.yml
   
   # Edit to enable ADCP_AUTH_TEST_MODE=true
   # Then start services
   docker-compose up
   ```

### Test Users (Defaults)

| Role | Email | Password | Customization |
|------|-------|----------|--------------|
| Super Admin | `test_super_admin@example.com` | `test123` | `TEST_SUPER_ADMIN_EMAIL/PASSWORD` |
| Tenant Admin | `test_tenant_admin@example.com` | `test123` | `TEST_TENANT_ADMIN_EMAIL/PASSWORD` |
| Tenant User | `test_tenant_user@example.com` | `test123` | `TEST_TENANT_USER_EMAIL/PASSWORD` |

**⚠️ WARNING**: Never enable test mode in production!

### Running UI Tests

```bash
# Run all UI tests
ADCP_AUTH_TEST_MODE=true uv run pytest tests/ui/ -v

# Run specific UI test
ADCP_AUTH_TEST_MODE=true uv run pytest tests/ui/test_auth_mode.py -v
```

## Simulations and Demos

### Running Full Lifecycle Simulation

The simulation demonstrates a complete campaign lifecycle:

```bash
# Run with temporary test database
uv run python tools/simulations/run_simulation.py

# Dry-run mode (shows API calls without executing)
uv run python tools/simulations/run_simulation.py --dry-run --adapter gam

# Use production database (careful!)
uv run python tools/simulations/run_simulation.py --use-prod-db
```

The simulation executes:
1. **Discovery** - AI analyzes brief and recommends products
2. **Creation** - Creates media buy with targeting
3. **Monitoring** - Simulates 90-day campaign with weekly reports

### Demo Scripts

Various demo scripts showcase specific features:

```bash
# AI product features
uv run python tools/demos/demo_ai_products.py

# Creative approval workflow
uv run python tools/demos/demo_creative_auto_approval.py

# Human task queue
uv run python tools/demos/demo_human_task_queue.py

# GAM integration
uv run python tools/demos/demo_gam_integration.py
```

## Coverage Reports

### Generate Coverage Report
```bash
# Run tests with coverage
uv run pytest --cov=. --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html
```

### Coverage Goals
- Unit tests: > 80% coverage
- Integration tests: > 60% coverage
- Overall: > 70% coverage

## Writing Tests

### Test Structure
```python
import pytest
from tests.fixtures import TenantFactory, PrincipalFactory

class TestFeatureName:
    """Tests for specific feature."""
    
    @pytest.fixture
    def setup_data(self):
        """Setup test data."""
        tenant = TenantFactory.create()
        principal = PrincipalFactory.create(tenant_id=tenant["tenant_id"])
        return tenant, principal
    
    def test_specific_behavior(self, setup_data):
        """Test description."""
        tenant, principal = setup_data
        # Test implementation
        assert result == expected
```

### Best Practices
1. **Use factories** for test data creation
2. **Mock external services** in unit tests
3. **Use real database** in integration tests
4. **Clean up resources** in teardown
5. **Test error cases** not just happy paths
6. **Keep tests focused** - one assertion per test when possible
7. **Use descriptive names** that explain what is being tested

## CI/CD Pipeline

Tests run automatically on push/PR via GitHub Actions:

### Pipeline Stages
1. **Lint & Format** - Code quality checks
2. **Unit Tests** - Fast feedback on code changes
3. **Integration Tests** - Component interaction validation
4. **Coverage Report** - Track test completeness

### Running CI Locally
```bash
# Simulate CI environment
./run_all_tests.sh ci

# Or with Python runner
uv run python scripts/run_tests.py all --ci
```

## Troubleshooting

### Common Issues

**Tests fail with "database not found"**
- Ensure database migrations are run: `uv run python migrate.py`
- Check DATABASE_URL environment variable

**Import errors**
- Install dependencies: `uv sync`
- Ensure virtual environment is activated

**Test authentication mode not working**
- Verify ADCP_AUTH_TEST_MODE=true is set
- Check no production OAuth credentials are interfering
- Ensure test users match environment variables

**Slow test execution**
- Use markers to skip slow tests: `pytest -m "not slow"`
- Run unit tests only for quick feedback: `pytest tests/unit/`

**Coverage gaps**
- Check htmlcov/index.html for uncovered lines
- Focus on critical business logic first
- Add tests for error handling paths

## Pre-Push Hooks

Git hooks ensure code quality before pushing:

### Setup
```bash
# Install hooks (once per workspace)
./setup_hooks.sh
```

### Hook Actions
1. **Format check** - Ensures code is properly formatted
2. **Lint check** - Catches common errors
3. **Unit tests** - Runs fast tests
4. **Coverage check** - Ensures minimum coverage

### Bypass (Emergency Only)
```bash
# Skip hooks if absolutely necessary
git push --no-verify
```

## Additional Resources

- [Fixture Guide](fixture-guide.md) - Working with test fixtures
- [CI/CD Workflow](.github/workflows/test.yml) - GitHub Actions configuration
- [pytest Documentation](https://docs.pytest.org/) - Official pytest docs