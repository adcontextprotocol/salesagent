# Testing Guide

## Overview

The AdCP Sales Agent test suite is organized into distinct categories to ensure comprehensive coverage while maintaining fast feedback loops. Tests are managed using `pytest` with `uv` for dependency management.

## Test Categories

### 1. Unit Tests (`tests/unit/`)
**Purpose**: Test individual components in isolation  
**Runtime**: < 1 second per test  
**Dependencies**: None (all external dependencies mocked)  

Examples:
- Schema validation
- Business logic functions
- Data transformations
- Utility functions

### 2. Integration Tests (`tests/integration/`)
**Purpose**: Test component interactions with real services  
**Runtime**: < 5 seconds per test  
**Dependencies**: Database (SQLite/PostgreSQL), mocked external APIs  

Examples:
- Database operations
- API endpoint behavior
- Multi-component workflows
- Session management

### 3. End-to-End Tests (`tests/e2e/`)
**Purpose**: Test complete user workflows  
**Runtime**: < 30 seconds per test  
**Dependencies**: Full system stack, may use real external services  

Examples:
- Complete campaign lifecycle
- Multi-tenant operations
- Real adapter integrations

### 4. UI Tests (`tests/ui/`)
**Purpose**: Test web interface functionality  
**Dependencies**: Flask test client, mocked OAuth  

Examples:
- Page rendering
- Form submissions
- Authentication flows
- JavaScript functionality

## Environment Setup

### Required Environment Variables

```bash
# Test Database (automatically set in CI)
DATABASE_URL=sqlite:///test.db  # or postgresql://...
ADCP_TESTING=true

# API Keys (can use mock values for most tests)
GEMINI_API_KEY=test_key_for_mocking
GOOGLE_CLIENT_ID=test_client_id
GOOGLE_CLIENT_SECRET=test_client_secret

# Admin Configuration
SUPER_ADMIN_EMAILS=test@example.com
SUPER_ADMIN_DOMAINS=example.com

# Optional: Test Authentication Mode
ADCP_AUTH_TEST_MODE=true  # Enables test login without OAuth
```

### Local Development Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Set up test database**:
   ```bash
   # SQLite (default for unit tests)
   export DATABASE_URL=sqlite:///test.db
   
   # PostgreSQL (for integration tests)
   docker run -d \
     --name adcp-test-db \
     -e POSTGRES_DB=adcp_test \
     -e POSTGRES_USER=adcp_user \
     -e POSTGRES_PASSWORD=test_password \
     -p 5432:5432 \
     postgres:15
   
   export DATABASE_URL=postgresql://adcp_user:test_password@localhost:5432/adcp_test
   ```

3. **Run migrations**:
   ```bash
   uv run python migrate.py
   ```

## Running Tests

### Using pytest directly

```bash
# Run all tests
uv run pytest

# Run specific category
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/

# Run specific test file
uv run pytest tests/unit/test_schemas.py

# Run specific test function
uv run pytest tests/unit/test_schemas.py::test_principal_validation

# Run with coverage
uv run pytest --cov=. --cov-report=html

# Run with verbose output
uv run pytest -v

# Run with specific markers
uv run pytest -m unit
uv run pytest -m "not slow"
uv run pytest -m ai
```

### Using the test runner script

```bash
# Run unit tests
uv run python scripts/run_tests.py unit

# Run integration tests
uv run python scripts/run_tests.py integration

# Run all tests
uv run python scripts/run_tests.py all

# List available categories
uv run python scripts/run_tests.py --list

# Run with coverage
uv run python scripts/run_tests.py unit --coverage

# Run specific test
uv run python scripts/run_tests.py --test tests/unit/test_schemas.py
```

## Test Markers

Tests can be marked with decorators to control execution:

```python
@pytest.mark.unit          # Fast, isolated unit test
@pytest.mark.integration   # Requires database/services
@pytest.mark.e2e          # Full system test
@pytest.mark.slow         # Takes > 5 seconds
@pytest.mark.ai           # Requires GEMINI_API_KEY
@pytest.mark.gam          # Requires GAM credentials
@pytest.mark.skip_ci      # Skip in CI environment
@pytest.mark.asyncio      # Async test function
```

## Writing Tests

### Test Structure

```python
import pytest
from unittest.mock import patch, MagicMock

class TestFeatureName:
    """Test suite for specific feature."""
    
    @pytest.fixture
    def setup_data(self):
        """Fixture for test data setup."""
        return {"key": "value"}
    
    def test_feature_success_case(self, setup_data):
        """Test successful operation."""
        # Arrange
        data = setup_data
        
        # Act
        result = function_under_test(data)
        
        # Assert
        assert result.status == "success"
        assert result.data == expected_data
    
    def test_feature_error_case(self):
        """Test error handling."""
        with pytest.raises(ValueError) as exc_info:
            function_under_test(invalid_data)
        
        assert "Invalid data" in str(exc_info.value)
```

### Mocking External Dependencies

```python
# Mock database connection
@pytest.fixture
def mock_db():
    with patch('module.get_db_connection') as mock:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = ('result',)
        conn.execute.return_value = cursor
        mock.return_value = conn
        yield conn

# Mock API calls
@patch('requests.post')
def test_api_call(mock_post):
    mock_post.return_value.json.return_value = {"status": "ok"}
    result = make_api_call()
    assert result["status"] == "ok"
```

### Testing Async Functions

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result == expected_value

# Or use pytest-asyncio fixtures
@pytest.fixture
async def async_client():
    async with AsyncClient() as client:
        yield client

@pytest.mark.asyncio
async def test_with_client(async_client):
    response = await async_client.get("/endpoint")
    assert response.status_code == 200
```

## CI/CD Integration

### GitHub Actions

The project uses GitHub Actions for continuous testing:

1. **Unit Tests**: Run on every push/PR
2. **Integration Tests**: Run on every push/PR with PostgreSQL
3. **E2E Tests**: Run only on main branch merges
4. **Lint & Format**: Check code style

### Coverage Reports

Coverage is automatically uploaded to Codecov:
- View reports at: https://codecov.io/gh/adcontextprotocol/salesagent
- Coverage badges show in README
- PR comments show coverage changes

## Performance Testing

### Marking Slow Tests

```python
@pytest.mark.slow
def test_heavy_computation():
    """This test takes > 5 seconds."""
    result = expensive_operation()
    assert result
```

### Benchmarking

```python
import pytest
import time

@pytest.fixture
def benchmark():
    """Simple benchmark fixture."""
    start = time.time()
    yield
    duration = time.time() - start
    print(f"\nTest duration: {duration:.2f}s")

def test_performance(benchmark):
    """Test with performance monitoring."""
    result = function_to_benchmark()
    assert result
    # Duration printed automatically
```

## Debugging Tests

### Verbose Output

```bash
# Show print statements
uv run pytest -s

# Show full traceback
uv run pytest --tb=long

# Stop on first failure
uv run pytest -x

# Enter debugger on failure
uv run pytest --pdb
```

### Test Isolation

```bash
# Run tests in random order to detect dependencies
uv run pytest --random-order

# Run each test in separate process
uv run pytest -n auto
```

## Common Issues

### 1. Database Connection Errors

**Problem**: Tests fail with "no such table" or connection errors  
**Solution**: 
- Ensure DATABASE_URL is set correctly
- Run migrations: `uv run python migrate.py`
- Check database is running (for PostgreSQL)

### 2. Import Errors

**Problem**: Tests fail with ImportError  
**Solution**:
- Mock imports that access database at module level
- Use proper fixture setup for database connections
- Check PYTHONPATH includes project root

### 3. Flaky Tests

**Problem**: Tests pass sometimes but fail others  
**Solution**:
- Use proper test isolation
- Mock time-dependent operations
- Clean up resources in teardown
- Use fixtures for consistent setup

### 4. OAuth/Authentication Issues

**Problem**: OAuth tests fail with 404 or auth errors  
**Solution**:
- Mock OAuth providers properly
- Use ADCP_AUTH_TEST_MODE for UI testing
- Ensure session setup in test fixtures

## Best Practices

1. **Keep tests fast**: Unit tests should run in < 1 second
2. **Use descriptive names**: `test_<what>_<condition>_<expected>`
3. **One assertion per test**: Makes failures clear
4. **Mock external dependencies**: Don't hit real APIs in unit tests
5. **Use fixtures**: Share setup code between tests
6. **Clean up resources**: Use try/finally or context managers
7. **Test edge cases**: Empty data, nulls, invalid inputs
8. **Document complex tests**: Add docstrings explaining the scenario
9. **Run tests before committing**: Use pre-commit hooks
10. **Monitor coverage**: Aim for > 80% coverage

## Test Data Management

### Fixtures Directory

```
tests/fixtures/
├── sample_products.json      # Product test data
├── sample_creatives.json     # Creative test data
├── mock_responses.py          # Mock API responses
└── test_database.sql          # Database seed data
```

### Using Test Data

```python
import json
from pathlib import Path

@pytest.fixture
def sample_products():
    """Load sample product data."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_products.json"
    with open(fixture_path) as f:
        return json.load(f)

def test_with_fixtures(sample_products):
    """Test using fixture data."""
    assert len(sample_products) > 0
```

## Continuous Improvement

### Adding New Tests

1. **Identify gaps**: Check coverage reports
2. **Write test first**: TDD approach
3. **Run locally**: Verify test passes
4. **Check CI**: Ensure test passes in CI
5. **Update documentation**: Document new test patterns

### Refactoring Tests

1. **Remove duplication**: Extract common fixtures
2. **Improve clarity**: Rename for better understanding
3. **Speed up slow tests**: Mock more, test less
4. **Group related tests**: Use test classes
5. **Update markers**: Ensure correct categorization