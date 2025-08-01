# UI Test Suite for AdCP Sales Agent Admin UI

This is a comprehensive UI testing framework for the AdCP Sales Agent Admin UI using Playwright and pytest.

## Features

- **Page Object Model**: Clean separation of test logic and page interactions
- **Async/Await Support**: Full support for modern async Python testing
- **Parallel Execution**: Run tests in parallel for faster feedback
- **Visual Testing**: Option to run tests with visible browser for debugging
- **Comprehensive Reporting**: HTML and Allure reports with screenshots
- **CI/CD Integration**: GitHub Actions workflow included
- **Cross-browser Support**: Test on Chromium, Firefox, and WebKit

## Project Structure

```
ui_tests/
├── conftest.py              # Pytest configuration and fixtures
├── requirements.txt         # Python dependencies
├── run_tests.py            # Test runner script
├── Makefile                # Convenient commands
├── README.md               # This file
├── .github/
│   └── workflows/
│       └── ui-tests.yml    # CI pipeline
├── pages/                  # Page Object Models
│   ├── base_page.py       # Base page class
│   ├── login_page.py      # Login page
│   ├── tenant_page.py     # Tenant management
│   └── operations_page.py # Operations dashboard
├── tests/                  # Test files
│   ├── test_authentication.py
│   ├── test_tenant_management.py
│   └── test_operations_dashboard.py
├── utils/                  # Utility modules
│   ├── test_data.py       # Test data generators
│   └── auth_helper.py     # Authentication helpers
├── fixtures/              # Test data files
├── reports/               # Test reports (generated)
└── screenshots/           # Test screenshots (generated)
```

## Installation

1. Install Python dependencies:
```bash
# From the project root
uv sync --extra ui-tests
```

2. Install Playwright browsers:
```bash
cd ui_tests
uv run python run_tests.py --install-browsers
# or
make install
```

## Authentication

The AdCP Admin UI uses Google OAuth for authentication. Since Google OAuth cannot be automated directly, use these approaches:

### Quick Start (Using Existing Session)

The dev environment maintains persistent sessions. If already logged in:

```python
# Check authentication status
uv run python -m pytest ui_tests/tests/test_authentication_example.py::TestAuthenticationExample::test_check_auth_status -v -s

# Save current auth state for reuse
uv run python -m pytest ui_tests/tests/test_authentication_example.py::TestAuthenticationExample::test_save_current_auth_state -v

# Use saved auth in tests
uv run python -m pytest ui_tests/tests/test_login_example.py::TestLoginExample::test_with_saved_auth_state -v
```

### Authentication Methods

1. **Use Existing Session** (easiest for local testing)
2. **Save and Reuse Auth State** (recommended for consistency)
3. **Add Test Auth Endpoint** (best for CI/CD - see AUTHENTICATION_GUIDE.md)

For detailed authentication guidance, see [AUTHENTICATION_GUIDE.md](AUTHENTICATION_GUIDE.md).

## Configuration

Create a `.env` file in the ui_tests directory:

```env
# Application URLs
BASE_URL=http://localhost:8001
MCP_URL=http://localhost:8080

# Test Credentials
TEST_ADMIN_EMAIL=admin@example.com
TEST_USER_EMAIL=user@example.com

# Test Configuration
HEADLESS=true
DEBUG=false
SCREENSHOT_ON_FAILURE=true

# OAuth Test Configuration (if needed)
TEST_OAUTH_CLIENT_ID=your-test-client-id
TEST_OAUTH_CLIENT_SECRET=your-test-client-secret
```

## Running Tests

### Using Make commands:

```bash
# Run all tests
make test

# Run specific test suites
make test-auth      # Authentication tests only
make test-tenant    # Tenant management tests
make test-ops       # Operations dashboard tests

# Run with visible browser
make test-headed

# Run in parallel
make test-parallel

# Generate HTML report
make test-report

# Debug mode
make debug
```

### Using the test runner directly:

```bash
# Run all tests
python run_tests.py

# Run specific test file
python run_tests.py tests/test_authentication.py

# Run tests matching pattern
python run_tests.py -k "login"

# Run with visible browser
python run_tests.py --headed

# Enable debug logging
python run_tests.py --debug --verbose

# Run in parallel with 4 workers
python run_tests.py -n 4

# Generate reports
python run_tests.py --report --allure
```

## Writing Tests

### Basic Test Structure

```python
import pytest
from playwright.async_api import Page
from ..pages.login_page import LoginPage
from ..utils.auth_helper import AuthHelper

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_feature_works(self, page: Page, base_url: str):
        # Arrange
        login_page = LoginPage(page, base_url)
        await AuthHelper.login_as_admin(page, base_url)
        
        # Act
        await login_page.goto_login()
        
        # Assert
        assert await login_page.is_logged_in()
```

### Page Object Pattern

```python
from .base_page import BasePage

class MyPage(BasePage):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        
        # Define selectors
        self.submit_button = 'button[type="submit"]'
        self.error_message = '.error-message'
    
    async def submit_form(self):
        await self.click(self.submit_button)
    
    async def get_error(self):
        return await self.get_text(self.error_message)
```

## Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.smoke      # Quick smoke tests
@pytest.mark.critical   # Critical path tests
@pytest.mark.slow       # Slow running tests
@pytest.mark.flaky      # Known flaky tests
```

Run tests by marker:
```bash
python run_tests.py -m smoke
python run_tests.py -m "not slow"
```

## Debugging

1. **Run with visible browser:**
   ```bash
   make debug
   # or
   python run_tests.py --headed --debug
   ```

2. **Take screenshots:**
   Screenshots are automatically taken on failure and saved to `screenshots/`

3. **Enable request logging:**
   Set `DEBUG=true` in `.env` or use `--debug` flag

4. **Use playwright inspector:**
   ```bash
   PWDEBUG=1 python -m pytest tests/test_authentication.py::test_login
   ```

## CI/CD Integration

The included GitHub Actions workflow:
- Sets up PostgreSQL test database
- Installs dependencies and browsers
- Starts application servers
- Runs tests in parallel
- Uploads test reports as artifacts
- Posts results to PR comments

## Best Practices

1. **Use Page Objects**: Keep selectors and page logic in page objects
2. **Avoid Hard Waits**: Use Playwright's built-in waiting mechanisms
3. **Test Data**: Use the TestDataGenerator for consistent test data
4. **Cleanup**: Tests should clean up after themselves
5. **Parallel Safety**: Ensure tests can run in parallel without conflicts
6. **Meaningful Names**: Use descriptive test and method names
7. **Error Messages**: Include helpful error messages in assertions

## Troubleshooting

### Common Issues:

1. **Timeout errors**: Increase timeout in conftest.py or specific tests
2. **Element not found**: Check selectors match current UI
3. **Authentication issues**: Verify test credentials are correct
4. **Port conflicts**: Ensure application is running on expected ports

### Debug Commands:

```bash
# List available browsers
playwright install --list

# Check Playwright version
playwright --version

# Run single test with maximum verbosity
pytest -vvs tests/test_authentication.py::TestAuthentication::test_google_oauth_login
```

## Contributing

1. Follow the existing patterns and structure
2. Add page objects for new pages
3. Write tests for new features
4. Ensure tests pass locally before pushing
5. Update this README if adding new functionality

## Future Enhancements

- [ ] Visual regression testing with screenshots
- [ ] Performance testing integration
- [ ] Accessibility testing
- [ ] Multi-browser testing in CI
- [ ] Test data management system
- [ ] Integration with test management tools