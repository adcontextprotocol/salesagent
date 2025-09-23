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

## MCP Tool Roundtrip Validation

### Critical Testing Pattern

The MCP tools use a roundtrip conversion pattern that requires special testing attention:

```python
# Pattern used in get_products and other MCP tools:
response_data = {"products": [p.model_dump_internal() for p in eligible_products]}
response_data = apply_testing_hooks(response_data, testing_ctx, "get_products")
modified_products = [Product(**p) for p in response_data["products"]]  # Critical conversion
```

### Why This Requires Testing

**The Issue**: Our Pydantic models use internal field names (`formats`) but AdCP spec requires external names (`format_ids`). The `model_dump()` method converts field names for AdCP compliance, but `model_dump_internal()` preserves internal names for roundtrip conversion.

**Production Impact**: A validation error "formats field required" occurred because tests used mock dictionaries instead of real Product objects, missing this conversion.

### Roundtrip Validation Tests

**Key Test Files:**
- `tests/integration/test_mcp_tool_roundtrip_validation.py` - Tests actual MCP tool execution paths
- `tests/integration/test_schema_roundtrip_patterns.py` - Reusable roundtrip validation patterns
- `tests/integration/test_schema_contract_validation.py` - AdCP spec compliance validation

**Critical Test Pattern:**
```python
# Test the actual roundtrip conversion that occurs in production
def test_product_roundtrip_conversion(self):
    # 1. Create real Product object
    product = Product(
        product_id="test",
        name="Test Product",
        formats=["display_300x250"],  # Internal field name
        delivery_type="non_guaranteed",
        is_fixed_price=False
    )

    # 2. Convert to internal dict (preserves field names)
    product_dict = product.model_dump_internal()

    # 3. Apply testing hooks (simulates production path)
    response_data = {"products": [product_dict]}
    response_data = apply_testing_hooks(response_data, testing_ctx, "get_products")

    # 4. Test reconstruction (this was failing in production)
    modified_products = [Product(**p) for p in response_data["products"]]

    # 5. Verify successful roundtrip
    assert modified_products[0].formats == ["display_300x250"]
```

### Testing Guidelines

**✅ DO:**
- Use real Product/Schema objects in tests
- Test the complete MCP tool execution path
- Validate both internal and external field mappings
- Test roundtrip conversions: Object → dict → Object

**❌ DON'T:**
- Use mock dictionaries that bypass Pydantic validation
- Test only isolated components without integration
- Skip testing hooks application
- Assume field name conversions work without testing

### Running Roundtrip Tests

```bash
# Run all roundtrip validation tests
uv run pytest tests/integration/test_mcp_tool_roundtrip_validation.py

# Run schema contract validation
uv run pytest tests/integration/test_schema_contract_validation.py

# Test specific roundtrip pattern
uv run pytest -k "roundtrip_conversion"
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

## Database Field Access Testing

This section addresses comprehensive testing strategies to prevent database field access bugs like the `'Product' object has no attribute 'pricing'` error that reached production (Issue #161).

### Problem Statement

Over-mocking of the database layer can hide real field access bugs:
- Tests mock ORM objects instead of using real database connections
- Schema validation happens after field access errors occur
- Missing integration between database and schema layers

### Testing Strategy

Our approach uses four complementary testing methods:

1. **Database Integration Tests** - Test actual ORM model to schema conversion with real database
2. **Schema-Database Mapping Validation** - Validate that schema fields align with database columns
3. **Real Data Flow Tests** - End-to-end testing with minimal mocking
4. **Pre-commit Hook Validation** - Automated prevention of field misalignment

### Key Test Files

- `tests/integration/test_get_products_database_integration.py` - Real database conversion testing
- `tests/integration/test_schema_database_mapping.py` - Field alignment validation
- `tests/integration/test_a2a_real_data_flow.py` - End-to-end data flow testing

### Recommended Testing Patterns

#### ❌ Problematic Pattern (Over-Mocking)
```python
@patch('product_catalog_providers.database.ProductModel')
def test_get_products(self, mock_product_model):
    mock_product = Mock()
    mock_product.pricing = 5.00  # Mock allows any attribute
    mock_product_model.query.return_value = [mock_product]

    # Test passes even though real ProductModel has no 'pricing' field
    result = get_products()
    assert result[0].pricing == 5.00
```

#### ✅ Better Pattern (Database Integration)
```python
def test_get_products_real_database(self, test_tenant_setup):
    # Use real database connection
    with get_db_session() as session:
        db_product = session.query(ProductModel).first()

        # This would fail if 'pricing' field doesn't exist
        assert hasattr(db_product, 'cpm')  # Real field
        assert not hasattr(db_product, 'pricing')  # Non-existent field

        # Test actual conversion
        catalog = DatabaseProductCatalog()
        products = await catalog.get_products(brief="test", tenant_id=tenant_id)
        assert products[0].cpm == 5.00  # Real field access
```

### Safe Field Access Patterns

When working with database models, use these patterns to avoid AttributeError:

```python
# Pattern 1: Direct access for known required fields
assert product.product_id == 'expected_id'

# Pattern 2: Conditional access for optional fields
cpm = getattr(product, 'cpm', None)

# Pattern 3: Check field existence before access
if hasattr(product, 'brief_relevance'):
    relevance = product.brief_relevance

# Pattern 4: Use model_dump() for safe dict access
product_dict = product.model_dump()
field_value = product_dict.get('optional_field')
```

### Running Database Field Access Tests

```bash
# All database field access tests
uv run pytest tests/integration/test_*database* tests/integration/test_*schema* -v

# Specific test files
uv run pytest tests/integration/test_get_products_database_integration.py -v
uv run pytest tests/integration/test_schema_database_mapping.py -v

# Field alignment validation (pre-commit hook)
uv run python scripts/validate_schema_database_alignment.py
```

### Pre-commit Hook Validation

The `schema-database-alignment` hook automatically validates field alignment:
- Runs when `src/core/schemas.py` or `src/core/database/models.py` change
- Prevents commits with missing database fields for schema properties
- Checks for unsafe field access patterns in code

### Troubleshooting Field Access Issues

**Error**: `'Product' object has no attribute 'pricing'`
**Solution**: Use the correct field name (`cpm`) or add the field to the database schema

**Error**: Schema validation fails with database data
**Solution**: Check field type conversions (e.g., `Decimal` → `float`) in the database provider

**Error**: Pre-commit hook fails with field alignment issues
**Solution**: Either add missing database columns or mark schema fields as `computed_fields`

For additional database field access safety patterns, see [Database Patterns - Field Access Safety](database-patterns.md#field-access-safety-testing).

### Integration Test Authentication

When writing integration tests that need authentication:

```python
@pytest.fixture
def auth_session(self, client, integration_db):
    """Create authenticated session with tenant management admin access."""
    from models import TenantManagementConfig
    from database_session import get_db_session

    # Set up tenant management admin in database
    with get_db_session() as session:
        email_config = TenantManagementConfig(
            config_key="super_admin_emails",
            config_value="test@example.com"
        )
        session.add(email_config)
        session.commit()

    # Set up session
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["email"] = "test@example.com"
        sess["role"] = "super_admin"
        sess["user"] = {"email": "test@example.com", "role": "super_admin"}

    return client
```

**Common Issues:**
- **403 Forbidden**: Missing TenantManagementConfig in database
- **302 Redirect**: Web routes redirect on success (not JSON)
- **Missing session["user"]**: `require_auth` needs both `authenticated` and `user`

### Model Requirements in Tests

```python
# Principal needs valid platform_mappings
principal = Principal(
    tenant_id="test",
    principal_id="test_principal",
    platform_mappings={"mock": {"advertiser_id": "test"}},  # NOT empty dict
)

# MediaBuy needs order_name and raw_request
media_buy = MediaBuy(
    media_buy_id="test_buy",
    order_name="Test Order",  # Required
    raw_request={},           # Required
    # ... other fields
)
```

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
