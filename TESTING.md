# AdCP Sales Agent - Testing Guide

This guide explains the automated testing setup for the AdCP Sales Agent project.

## Overview

We have a comprehensive testing infrastructure that includes:
- **Unified test runner** for all tests
- **GitHub Actions** for CI/CD
- **Pre-push hooks** for local quality assurance
- **Coverage reporting** to track test completeness

## Quick Start

### 1. Initial Setup

```bash
# Install Git hooks (required for each workspace/worktree)
./setup_hooks.sh

# Run all tests
./run_all_tests.sh
```

**Note for Conductor users**: Git hooks are per-worktree, so you need to run `setup_hooks.sh` in each workspace. The `setup_conductor_workspace.sh` script now does this automatically.

### 2. Running Tests

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

## Test Suite Components

### Test Organization

Tests are organized in the `tests/` directory:
- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests (future)

### Current Working Tests

1. **tests/unit/test_admin_ui_oauth.py** - OAuth authentication flows (33 tests) ✅

### Legacy Test Files (to be migrated)

These tests currently exist in the root directory and need migration:
- **test_auth.py** - MCP authentication
- **test_adapter_targeting.py** - Ad server adapter targeting
- **test_creative_auto_approval.py** - Creative approval workflows
- **test_admin_creative_approval.py** - Admin creative management
- **test_human_task_queue.py** - Human-in-the-loop tasks
- **test_manual_approval.py** - Manual approval processes
- **test_task_verification.py** - Task verification
- **test_product_catalog_providers.py** - Product catalog
- **test_main.py** - Core MCP server functionality
- **tests/test_adapters.py** - Ad server adapters

**Note**: The legacy tests have import issues due to database initialization on module import. These need refactoring to properly isolate test environments.

### Test Dependencies

The test suite automatically installs required dependencies:
- pytest, pytest-mock, pytest-cov
- All project dependencies (pydantic, sqlalchemy, flask, etc.)

## GitHub Actions CI/CD

The project uses GitHub Actions for automated testing on every push and PR.

### Workflow Features

- **Python 3.12**: Tests run on Python 3.12 as required by the project
- **PostgreSQL service**: Real database for integration tests
- **Coverage reporting**: Automatic upload to Codecov
- **Artifact storage**: Test results and coverage reports
- **Caching**: Faster builds with pip cache

### CI Configuration

The workflow is defined in `.github/workflows/test.yml` and runs:
- On pushes to `main` and `develop` branches
- On all pull requests to `main`

## Pre-Push Hook

The pre-push hook automatically runs tests before pushing to prevent broken code from reaching the repository.

### Features

- Runs quick tests before each push
- Clear error messages if tests fail
- Option to bypass with `--no-verify` flag

### Usage

```bash
# Normal push (runs tests)
git push

# Skip tests (not recommended)
git push --no-verify
```

## Coverage Reports

Track test coverage to ensure comprehensive testing:

```bash
# Generate coverage report
./run_all_tests.sh coverage

# View HTML report
open htmlcov/index.html
```

### Coverage Configuration

The `.coveragerc` file configures coverage to:
- Exclude test files and virtual environments
- Skip abstract methods and type checking blocks
- Generate both terminal and HTML reports

## Writing New Tests

### Test Structure

1. Place test files in the root directory with `test_` prefix
2. Use pytest fixtures for setup/teardown
3. Mock external dependencies
4. Follow existing patterns in the codebase

### Example Test

```python
import pytest
from unittest.mock import Mock, patch

def test_example_feature():
    """Test description."""
    # Arrange
    mock_dependency = Mock()
    
    # Act
    result = function_under_test(mock_dependency)
    
    # Assert
    assert result == expected_value
    mock_dependency.assert_called_once()
```

## Best Practices

1. **Run tests before committing**: Use the pre-push hook
2. **Write tests for new features**: Aim for high coverage
3. **Use mocking**: Avoid external dependencies in tests
4. **Keep tests fast**: Quick feedback loop
5. **Test edge cases**: Not just happy paths

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure all dependencies are installed
   ```bash
   pip install -r requirements.txt  # if available
   # or
   ./run_all_tests.sh  # auto-installs dependencies
   ```

2. **Database errors**: Tests use mocking, but some may need:
   ```bash
   export DATABASE_URL=sqlite:///test.db
   ```

3. **Permission errors**: Make scripts executable
   ```bash
   chmod +x run_all_tests.sh setup_hooks.sh
   ```

### Debug Mode

For detailed test output:
```bash
# See all print statements and full tracebacks
./run_all_tests.sh verbose

# Run specific test file
pytest test_admin_ui_oauth.py -v

# Run specific test
pytest test_admin_ui_oauth.py::TestOAuthLogin::test_login_page_renders -v
```

## Contributing

When contributing to the project:

1. **Install hooks**: Run `./setup_hooks.sh`
2. **Write tests**: Add tests for new features
3. **Run tests**: Use `./run_all_tests.sh` before pushing
4. **Check coverage**: Ensure no decrease in coverage
5. **Update this doc**: Document new test patterns

## Future Improvements

- [ ] Add integration tests with real services
- [ ] Implement performance benchmarks
- [ ] Add mutation testing
- [ ] Create test data fixtures
- [ ] Add API contract tests