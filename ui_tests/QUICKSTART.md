# UI Tester Quick Start Guide

## Setup (Already Completed)

The UI testing framework has been set up with:
- Playwright for browser automation
- pytest-playwright for async test support
- Page Object Model pattern
- Comprehensive test utilities

## Running Tests

### 1. Basic Commands

```bash
# Run all UI tests
cd /Users/brianokelley/Developer/salesagent/.conductor/phuket
uv run python -m pytest ui_tests/tests/ -v

# Run specific test file
uv run python -m pytest ui_tests/tests/test_basic_setup.py -v

# Run with visible browser (headed mode)
HEADLESS=false uv run python -m pytest ui_tests/tests/test_basic_setup.py -v

# Run specific test
uv run python -m pytest ui_tests/tests/test_basic_setup.py::TestBasicSetup::test_browser_launches -v
```

### 2. Using Make Commands

```bash
cd ui_tests

# Run all tests
make test

# Run with visible browser
make test-headed

# Run specific test suites
make test-auth
make test-tenant
make test-ops

# Generate HTML report
make test-report
```

### 3. Current Test Status

✅ **Working Tests:**
- Basic setup tests (browser launch, navigation, screenshots)
- All 5 basic tests are passing

⚠️ **Tests Needing Adjustment:**
- Authentication tests - need to handle already logged-in state
- Tenant management tests - require proper test data setup
- Operations dashboard tests - depend on existing data

## Key Findings

1. **Application State**: The Admin UI (http://localhost:8001) is already logged in as `dev@example.com` with Super Admin access
2. **No Traditional Login**: The app redirects logged-in users directly to the tenant list
3. **Docker Containers**: Multiple workspace containers are running (kabul on 8001/8080)

## Writing New Tests

### Example Test Structure

```python
import pytest
from playwright.async_api import Page
from ..pages.base_page import BasePage

class TestNewFeature:
    @pytest.mark.asyncio
    async def test_feature(self, page: Page, base_url: str):
        # Navigate
        await page.goto(base_url)
        
        # Interact
        await page.click('button.my-button')
        
        # Assert
        assert await page.is_visible('.success-message')
```

### Page Object Example

```python
from .base_page import BasePage

class MyPage(BasePage):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        self.my_button = 'button.my-button'
        
    async def click_my_button(self):
        await self.click(self.my_button)
```

## Debugging Tips

1. **View Browser**: Set `HEADLESS=false` to see what's happening
2. **Screenshots**: Automatically taken on failure in `screenshots/` directory
3. **Debug Mode**: Set `DEBUG=true` to see HTTP requests/responses
4. **Playwright Inspector**: Use `PWDEBUG=1` for step-by-step debugging

## Next Steps

1. **Logout/Login Flow**: Implement proper logout before authentication tests
2. **Test Data Setup**: Create fixtures for test tenants/principals
3. **CI Integration**: The GitHub Actions workflow is ready but needs environment setup
4. **More Page Objects**: Add page objects for products, creatives, etc.

## Environment Variables

Create a `.env` file in the ui_tests directory:

```env
BASE_URL=http://localhost:8001
HEADLESS=true
DEBUG=false
TEST_ADMIN_EMAIL=admin@example.com
```

## Troubleshooting

If tests fail:
1. Check if Admin UI is running: `curl http://localhost:8001`
2. Check browser installation: `uv run playwright install chromium`
3. Clear cookies/session: Tests may need to handle existing sessions
4. Check screenshots in `ui_tests/screenshots/`