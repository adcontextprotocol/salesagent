# Authentication Guide for UI Testing

The AdCP Admin UI uses Google OAuth exclusively for authentication. This guide shows how to handle authentication in your UI tests.

## Current Situation

- **Authentication Method**: Google OAuth only (no username/password login)
- **Session Management**: Flask sessions with cookies
- **Current State**: The dev environment appears to have persistent sessions (stays logged in)

## Authentication Options for Testing

### Option 1: Use Existing Session (Easiest for Local Testing)

If the application is already logged in (as appears to be the case in the dev environment):

```python
from ..utils.session_auth import SessionAuth

# Check if already logged in
auth_status = await SessionAuth.check_current_auth(page)
if auth_status["logged_in"]:
    print(f"Already logged in as {auth_status['email']}")
    # Proceed with tests
```

### Option 2: Save and Reuse Authentication State (Recommended)

1. **Save authentication state after manual login:**

```bash
# Run this test to save current auth state
uv run python -m pytest ui_tests/tests/test_authentication_example.py::TestAuthenticationExample::test_save_current_auth_state -v
```

2. **Use saved state in tests:**

```python
@pytest.fixture(scope="session")
async def authenticated_browser(browser):
    """Create browser context with saved authentication."""
    context = await browser.new_context(storage_state="test_auth_state.json")
    yield context
    await context.close()

@pytest.fixture
async def authenticated_page(authenticated_browser):
    """Create authenticated page."""
    page = await authenticated_browser.new_page()
    yield page
    await page.close()

# Use in test
async def test_something(authenticated_page: Page):
    await authenticated_page.goto("/")
    # Already logged in!
```

### Option 3: Add Test Authentication Endpoint (Best for CI/CD)

1. **Add test auth endpoint to admin_ui.py:**

```python
# Add this to admin_ui.py (before if __name__ == '__main__':)
if os.environ.get('ENABLE_TEST_AUTH') == 'true':
    @app.route('/test/auth/login', methods=['POST'])
    def test_auth_login():
        if os.environ.get('FLASK_ENV') != 'development':
            return jsonify({"error": "Test auth only available in development"}), 403
        
        data = request.get_json() or request.form
        session['authenticated'] = True
        session['role'] = data.get('role', 'super_admin')
        session['email'] = data.get('email', 'test@example.com')
        session['username'] = data.get('username', 'Test User')
        
        return jsonify({"success": True})
```

2. **Use in tests:**

```python
async def login_test_user(page: Page, email: str, role: str = "super_admin"):
    response = await page.request.post("/test/auth/login", data={
        "email": email,
        "role": role
    })
    assert response.ok
    await page.goto("/")  # Refresh to apply session
```

## Environment Variables

Add these to your `.env` file:

```env
# Test credentials (for reference, not used with OAuth)
TEST_ADMIN_EMAIL=admin@example.com
TEST_USER_EMAIL=user@example.com

# Enable test auth endpoint (if added)
ENABLE_TEST_AUTH=true
FLASK_ENV=development
```

## Practical Examples

### 1. Test that Requires Admin Access

```python
class TestAdminFeatures:
    @pytest.mark.asyncio
    async def test_create_tenant(self, page: Page, base_url: str):
        # Ensure we're logged in as admin
        auth = await SessionAuth.check_current_auth(page)
        
        if not auth["logged_in"] or auth["role"] != "super_admin":
            pytest.skip("Requires super admin access")
        
        # Proceed with test
        await page.goto(f"{base_url}/create_tenant")
        # ... rest of test
```

### 2. Test Different User Roles

```python
@pytest.mark.parametrize("role,expected_access", [
    ("super_admin", True),
    ("admin", True),
    ("viewer", False),
])
async def test_access_control(authenticated_page: Page, role: str, expected_access: bool):
    # This would require setting up different authenticated contexts
    # or using the test auth endpoint to switch roles
    pass
```

### 3. Logout Test

```python
async def test_logout(page: Page, base_url: str):
    # Ensure logged in first
    auth = await SessionAuth.check_current_auth(page)
    if not auth["logged_in"]:
        pytest.skip("Need to be logged in to test logout")
    
    # Logout
    await page.click('a[href="/logout"]')
    await page.wait_for_load_state("networkidle")
    
    # Verify logged out (may auto-login again in dev)
    final_auth = await SessionAuth.check_current_auth(page)
    # Check appropriately based on your setup
```

## Running Authentication Tests

```bash
# Check current auth status
uv run python -m pytest ui_tests/tests/test_authentication_example.py::TestAuthenticationExample::test_check_auth_status -v -s

# Save auth state
uv run python -m pytest ui_tests/tests/test_authentication_example.py::TestAuthenticationExample::test_save_current_auth_state -v

# Run all auth examples
uv run python -m pytest ui_tests/tests/test_authentication_example.py -v -s
```

## Recommendations

1. **For Local Development**: Use the existing persistent session
2. **For CI/CD**: Add the test auth endpoint to admin_ui.py
3. **For Shared Environments**: Use saved authentication state files
4. **For Security**: Never commit real credentials or auth state files

## Troubleshooting

- **"Not logged in" errors**: The dev environment may have persistent sessions. Try accessing the UI manually first.
- **OAuth popup issues**: Real Google OAuth cannot be automated. Use one of the alternatives above.
- **Session expires**: Re-save the auth state file or re-login manually.