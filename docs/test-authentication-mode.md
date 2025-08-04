# Test Authentication Mode

## Overview

The AdCP Admin UI includes a test authentication mode that bypasses Google OAuth for automated testing. This feature is designed specifically for:

- Automated UI testing (Selenium, Playwright, etc.)
- CI/CD pipeline integration
- Development and debugging
- API testing without OAuth complexity

**⚠️ IMPORTANT: This mode should NEVER be enabled in production environments!**

## Enabling Test Mode

Test mode is controlled by the `ADCP_AUTH_TEST_MODE` environment variable:

```bash
# Enable test mode
export ADCP_AUTH_TEST_MODE=true

# Start the admin UI with test mode enabled
docker-compose up

# Or for local development
ADCP_AUTH_TEST_MODE=true python admin_ui.py
```

## Visual Indicators

When test mode is enabled, you'll see:

1. **Console Warning**: On startup, a warning message is printed
2. **Login Page Banner**: Orange warning banner on login pages
3. **Global Header Banner**: Fixed warning banner on all authenticated pages
4. **Test Login Form**: Additional form on login pages for test users

## Available Test Users

Three pre-configured test users are available:

| Email | Role | Password | Notes |
|-------|------|----------|-------|
| `test_super_admin@example.com` | Super Admin | `test123` | Full system access |
| `test_tenant_admin@example.com` | Tenant Admin | `test123` | Requires tenant_id |
| `test_tenant_user@example.com` | Tenant User | `test123` | Requires tenant_id |

## Usage Methods

### Method 1: Web UI Login

1. Navigate to `/login` (super admin) or `/tenant/{tenant_id}/login` (tenant users)
2. Use the test login form that appears below the Google sign-in button
3. Select a test user and enter the password

### Method 2: Direct Test Login Page

Navigate to `/test/login` for a dedicated test login interface with all available test users listed.

### Method 3: Programmatic Login

POST to `/test/auth` with credentials:

```python
import requests

session = requests.Session()
response = session.post('http://localhost:8001/test/auth', data={
    'email': 'test_super_admin@example.com',
    'password': 'test123',
    'tenant_id': 'tenant_123'  # Optional, for tenant users
})
```

## Example: Selenium Testing

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

# Ensure test mode is enabled
os.environ['ADCP_AUTH_TEST_MODE'] = 'true'

driver = webdriver.Chrome()
driver.get('http://localhost:8001/login')

# Use test login form
email_select = Select(driver.find_element(By.NAME, 'email'))
email_select.select_by_value('test_super_admin@example.com')

password_field = driver.find_element(By.NAME, 'password')
password_field.send_keys('test123')

submit_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
submit_button.click()

# Now authenticated and can test protected pages
```

## Example: Playwright Testing

```javascript
const { test, expect } = require('@playwright/test');

test('admin dashboard access', async ({ page }) => {
  // Ensure ADCP_AUTH_TEST_MODE=true is set
  
  await page.goto('http://localhost:8001/test/login');
  
  await page.selectOption('select[name="email"]', 'test_super_admin@example.com');
  await page.fill('input[name="password"]', 'test123');
  await page.click('button[type="submit"]');
  
  // Verify redirect to dashboard
  await expect(page).toHaveURL(/.*\/$/);
  await expect(page.locator('text=Tenants')).toBeVisible();
});
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run UI Tests
  env:
    ADCP_AUTH_TEST_MODE: true
  run: |
    docker-compose up -d
    pytest tests/ui/
```

### Jenkins Example

```groovy
stage('UI Tests') {
    environment {
        ADCP_AUTH_TEST_MODE = 'true'
    }
    steps {
        sh 'docker-compose up -d'
        sh 'python -m pytest tests/ui/'
    }
}
```

## Security Considerations

1. **Environment Check**: Test mode only works when explicitly enabled
2. **No Real Authentication**: Test users are hardcoded and don't exist in the database
3. **Visual Warnings**: Multiple indicators ensure users know they're in test mode
4. **404 on Disabled**: Test endpoints return 404 when test mode is disabled

## Best Practices

1. **Never commit** `.env` files with `ADCP_AUTH_TEST_MODE=true`
2. **Use separate environments** for testing (not production databases)
3. **Add checks in tests** to ensure test mode is enabled before running
4. **Document** in your test suite that test mode is required
5. **Monitor** production logs for any test mode activation attempts

## Troubleshooting

### Test mode not working
- Verify `ADCP_AUTH_TEST_MODE=true` is set
- Check console output for the warning message
- Ensure you're using the correct URLs (`/test/auth`, `/test/login`)

### Can't access test endpoints
- Returns 404 if test mode is disabled
- Check environment variable is properly set
- Restart the application after setting the variable

### Session issues
- Test users don't persist across server restarts
- Use the exact email addresses provided
- Password is always `test123`

## Docker Compose Configuration

### Using Docker Compose Override Files

**IMPORTANT**: Never modify the main `docker-compose.yml` file for testing. Instead, use Docker Compose's override mechanism:

1. Copy the example override file:
   ```bash
   cp docker-compose.override.example.yml docker-compose.override.yml
   ```

2. Uncomment the test mode section in your `docker-compose.override.yml`:
   ```yaml
   services:
     admin-ui:
       environment:
         - ADCP_AUTH_TEST_MODE=true
   ```

3. Docker Compose automatically loads `docker-compose.override.yml` when you run:
   ```bash
   docker-compose up
   ```

This approach keeps your main configuration clean and makes it easy to toggle test mode without affecting the core setup.

## Example Test Scripts

See the following example scripts in the repository:
- `test_auth_mode_example.py` - Basic usage demonstration
- `test_selenium_example.py` - Selenium browser automation example
- `docker-compose.override.example.yml` - Example override configuration