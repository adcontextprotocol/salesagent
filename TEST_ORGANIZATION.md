# Test Organization Plan

## Status Summary (Updated: January 2025)

### Test Results
- **Unit Tests**: ✅ All 51 tests passing (1 skipped - requires real API key)
- **Integration Tests**: ⚠️ 28 passing, 8 failing, 8 skipped, 3 errors
  - Most failures due to missing server or API configuration
  - Core functionality tests passing
- **End-to-End Tests**: Not run (requires running server)

### Reorganization Complete
- ✅ All test files moved from root to organized directories
- ✅ Comprehensive fixture system implemented
- ✅ CI/CD workflow updated with proper structure
- ✅ Documentation updated across all relevant files

## Directory Structure

```
tests/
├── __init__.py
├── conftest.py                 # Shared pytest fixtures
├── unit/                       # Fast, isolated unit tests
│   ├── __init__.py
│   ├── adapters/              # Adapter-specific tests
│   │   ├── test_base.py
│   │   ├── test_google_ad_manager.py
│   │   └── test_mock.py
│   ├── test_schemas.py        # Data model tests
│   ├── test_targeting.py      # Targeting system tests
│   ├── test_creative_parsing.py  # Creative format parsing
│   ├── test_auth.py           # Authentication tests
│   └── test_utils.py          # Utility function tests
├── integration/               # Tests requiring database/external services
│   ├── __init__.py
│   ├── test_main.py          # MCP server integration
│   ├── test_admin_ui.py      # Admin UI integration
│   ├── test_database.py      # Database operations
│   ├── test_creative_approval.py  # Creative workflow
│   ├── test_human_tasks.py   # Human-in-the-loop
│   ├── test_audit_logging.py # Audit system
│   └── test_ai_products.py   # AI product features
├── e2e/                       # End-to-end tests
│   ├── __init__.py
│   ├── test_full_campaign.py # Full campaign lifecycle
│   ├── test_multi_tenant.py  # Multi-tenant scenarios
│   └── test_gam_integration.py  # Real GAM integration
├── ui/                        # UI-specific tests
│   ├── __init__.py
│   ├── test_auth_mode.py     # Test authentication mode
│   ├── test_admin_pages.py   # Admin UI pages
│   └── test_gam_viewer.py    # GAM line item viewer
├── fixtures/                  # Test data and fixtures
│   ├── __init__.py
│   ├── sample_products.json
│   ├── sample_creatives.json
│   └── mock_responses.py
└── utils/                     # Test utilities
    ├── __init__.py
    ├── database.py           # Database helpers
    ├── mock_adapter.py       # Mock adapter helpers
    └── api_client.py         # Test API client

tools/                         # Development tools (not tests)
├── demos/                     # Demo scripts
│   ├── demo_dry_run.py
│   ├── demo_ai_products.py
│   ├── demo_creative_approval.py
│   └── demo_human_tasks.py
└── simulations/              # Simulation scripts
    ├── run_simulation.py
    └── simulation_full.py

scripts/                       # Operational scripts
├── run_tests.py              # Test runner
├── run_server.py             # Server launcher
├── run_admin_ui.py           # Admin UI launcher
└── check_ci.py               # CI checker
```

## Test Categories

### Unit Tests (`tests/unit/`)
- **Purpose**: Test individual components in isolation
- **Dependencies**: None (mocked)
- **Runtime**: < 1 second per test
- **Examples**:
  - Schema validation
  - Adapter interface compliance
  - Utility function behavior
  - Creative format parsing

### Integration Tests (`tests/integration/`)
- **Purpose**: Test component interactions
- **Dependencies**: Database, may use test API keys
- **Runtime**: < 5 seconds per test
- **Examples**:
  - Database operations
  - MCP server endpoints
  - Admin UI routes
  - Creative approval workflow

### End-to-End Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows
- **Dependencies**: Full system, may use real services
- **Runtime**: < 30 seconds per test
- **Examples**:
  - Complete campaign lifecycle
  - Multi-tenant scenarios
  - Real adapter integration

### UI Tests (`tests/ui/`)
- **Purpose**: Test web interface functionality
- **Dependencies**: Admin UI server
- **Runtime**: Variable
- **Examples**:
  - Page rendering
  - Form submission
  - OAuth flow
  - JavaScript functionality

## File Mapping

### Current → New Location

#### Unit Tests
- `test_adapters.py` → `tests/unit/adapters/test_base.py`
- `test_adapter_targeting.py` → `tests/unit/test_targeting.py`
- `test_creative_format_parsing.py` → `tests/unit/test_creative_parsing.py`
- `test_ai_parsing_improvements.py` → `tests/unit/test_creative_parsing.py` (merge)
- `test_format_json.py` → `tests/unit/test_creative_parsing.py` (merge)
- `test_auth.py` → `tests/unit/test_auth.py`
- `tests/unit/test_admin_ui_oauth.py` → Keep location

#### Integration Tests
- `test_main.py` → `tests/integration/test_main.py`
- `test_admin_creative_approval.py` → `tests/integration/test_creative_approval.py`
- `test_creative_auto_approval.py` → `tests/integration/test_creative_approval.py` (merge)
- `test_creative_format_updates.py` → `tests/integration/test_creative_approval.py` (merge)
- `test_human_task_queue.py` → `tests/integration/test_human_tasks.py`
- `test_manual_approval.py` → `tests/integration/test_human_tasks.py` (merge)
- `test_task_verification.py` → `tests/integration/test_human_tasks.py` (merge)
- `test_ai_product_features.py` → `tests/integration/test_ai_products.py`
- `test_ai_product_basic.py` → `tests/integration/test_ai_products.py` (merge)
- `test_product_catalog_providers.py` → `tests/integration/test_ai_products.py` (merge)
- `test_ai_quick.py` → `tests/integration/test_ai_products.py` (merge)
- `test_policy_check.py` → `tests/integration/test_policy.py`
- `test_superadmin_api.py` → `tests/integration/test_admin_api.py`
- `test_superadmin_api_integration.py` → `tests/integration/test_admin_api.py` (merge)
- `test_superadmin_api_unit.py` → `tests/unit/test_admin_api.py`

#### E2E Tests
- `test_gam_simple_display.py` → `tests/e2e/test_gam_integration.py`
- `test_line_item_api.py` → `tests/e2e/test_gam_integration.py` (merge)
- `test_line_item_mock.py` → `tests/integration/test_mock_adapter.py`

#### UI Tests
- `tests/ui/test_auth_mode.py` → Keep location
- `tests/ui/test_gam_line_item_viewer_ui.py` → Keep location (rename to test_gam_viewer.py)
- `test_nytimes_parsing.py` → `tests/ui/test_parsing_ui.py`
- `simple_parsing_test.py` → `tests/ui/test_parsing_ui.py` (merge)

#### Tools
- `demo_*.py` → `tools/demos/`
- `simulation_full.py` → `tools/simulations/`
- `run_simulation.py` → `tools/simulations/`

#### Scripts
- `run_tests.py` → `scripts/`
- `run_server.py` → `scripts/`
- `run_admin_ui.py` → `scripts/`
- `run_unified*.py` → `scripts/`
- `test_ci_locally.py` → `scripts/check_ci.py`

## Testing Best Practices

### 1. Test Naming
- Use descriptive names: `test_<what>_<condition>_<expected_result>`
- Example: `test_create_media_buy_with_invalid_budget_raises_error`

### 2. Test Structure
```python
def test_example():
    # Arrange - Set up test data
    data = create_test_data()
    
    # Act - Perform the action
    result = function_under_test(data)
    
    # Assert - Verify the result
    assert result.status == "success"
```

### 3. Fixtures
- Use pytest fixtures for reusable setup
- Keep fixtures in appropriate conftest.py
- Use scope wisely (function, class, module, session)

### 4. Mocking
- Mock external dependencies in unit tests
- Use real implementations in integration tests
- Document what's mocked and why

### 5. Database Testing
- Use isolated test database
- Clean up after each test
- Use transactions for speed

### 6. Async Testing
- Use `pytest-asyncio` for async tests
- Mark async tests with `@pytest.mark.asyncio`
- Handle cleanup properly

## Running Tests

### All Tests
```bash
pytest
```

### By Category
```bash
# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# E2E tests
pytest tests/e2e/
```

### With Coverage
```bash
pytest --cov=. --cov-report=html
```

### Specific Test
```bash
pytest tests/unit/test_schemas.py::test_principal_validation
```

### With Markers
```bash
# Skip slow tests
pytest -m "not slow"

# Only AI tests
pytest -m "ai"
```

## CI/CD Integration

### GitHub Actions Workflow
```yaml
- name: Run Unit Tests
  run: pytest tests/unit/ -v

- name: Run Integration Tests
  run: pytest tests/integration/ -v
  env:
    DATABASE_URL: postgresql://...

- name: Run E2E Tests
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: pytest tests/e2e/ -v
```

## Test Markers

```python
@pytest.mark.unit          # Fast, isolated unit test
@pytest.mark.integration   # Requires database/services
@pytest.mark.e2e          # Full system test
@pytest.mark.slow         # Takes > 5 seconds
@pytest.mark.ai           # Requires AI API key
@pytest.mark.gam          # Requires GAM credentials
@pytest.mark.skip_ci      # Skip in CI environment
```

## Environment Variables for Testing

```bash
# Required for all tests
DATABASE_URL=sqlite:///test.db

# Optional for specific tests
GEMINI_API_KEY=xxx        # For AI tests
GAM_NETWORK_CODE=xxx      # For GAM tests
ADCP_AUTH_TEST_MODE=true  # For UI tests
```