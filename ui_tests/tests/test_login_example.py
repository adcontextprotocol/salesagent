"""
Practical example of handling login in tests.
"""

import pytest
import os
from playwright.async_api import Page, Browser
from ..utils.session_auth import SessionAuth

class TestLoginExample:
    """Practical login examples."""
    
    @pytest.mark.asyncio
    async def test_with_existing_session(self, page: Page, base_url: str):
        """Use existing session if available."""
        # Navigate to the app
        await page.goto(base_url)
        
        # Check if already logged in
        auth_status = await SessionAuth.check_current_auth(page)
        
        if auth_status["logged_in"]:
            print(f"\n✅ Already logged in as: {auth_status['email']}")
            print(f"   Role: {auth_status['role']}")
            
            # Proceed with your test
            # For example, navigate to tenant management
            await page.click('a:has-text("Tenants")')
            assert "Default Publisher" in await page.content()
        else:
            print("\n❌ Not logged in")
            print("   Please login manually or use saved auth state")
            pytest.skip("Not logged in")
    
    @pytest.mark.asyncio
    async def test_with_saved_auth_state(self, browser: Browser, base_url: str):
        """Use saved authentication state."""
        auth_file = "test_auth_state.json"
        
        if not os.path.exists(auth_file):
            pytest.skip(f"No saved auth state at {auth_file}")
        
        # Create context with saved auth
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        # Navigate - should be already authenticated
        await page.goto(base_url)
        
        # Verify logged in
        auth_status = await SessionAuth.check_current_auth(page)
        assert auth_status["logged_in"], "Should be logged in with saved state"
        
        print(f"\n✅ Logged in using saved state: {auth_status['email']}")
        
        # Your test logic here
        assert "AdCP Sales Agent Admin" in await page.content()
        
        # Cleanup
        await page.close()
        await context.close()
    
    @pytest.mark.asyncio
    async def test_login_flow_demonstration(self, page: Page, base_url: str):
        """
        Demonstrate the complete login flow.
        This shows what happens when you try to login with credentials.
        """
        # Parameters from environment or defaults
        email = os.getenv("TEST_ADMIN_EMAIL", "admin@example.com")
        password = os.getenv("TEST_ADMIN_PASSWORD", "not-used-with-oauth")
        
        print(f"\n📧 Attempting to login as: {email}")
        
        # Check current state
        initial_auth = await SessionAuth.check_current_auth(page)
        print(f"Initial state: {'Logged in' if initial_auth['logged_in'] else 'Not logged in'}")
        
        if initial_auth["logged_in"] and initial_auth["email"] == email:
            print("✅ Already logged in with target email")
            return
        
        # Try to login
        result = await SessionAuth.login_with_credentials(page, base_url, email, password)
        
        if not result:
            print("\n⚠️  Cannot automate Google OAuth login")
            print("Please use one of these alternatives:")
            print("1. Save auth state after manual login (recommended)")
            print("2. Add test auth endpoint to the application")
            print("3. Use existing session")

# Fixture for pre-authenticated page
@pytest.fixture
async def authenticated_page(browser: Browser, base_url: str) -> Page:
    """Create a page with authentication already set up."""
    auth_file = "test_auth_state.json"
    
    if os.path.exists(auth_file):
        # Use saved auth state
        context = await browser.new_context(storage_state=auth_file)
    else:
        # Use default context and hope for existing session
        context = await browser.new_context()
    
    page = await context.new_page()
    await page.goto(base_url)
    
    # Verify authentication
    auth_status = await SessionAuth.check_current_auth(page)
    if not auth_status["logged_in"]:
        await page.close()
        await context.close()
        pytest.skip("Authentication required - please login first")
    
    yield page
    
    await page.close()
    await context.close()

class TestWithAuthentication:
    """Tests that require authentication."""
    
    @pytest.mark.asyncio
    async def test_authenticated_access(self, authenticated_page: Page):
        """Test that uses pre-authenticated page."""
        # This test will skip if not authenticated
        print("\n✅ Using pre-authenticated page")
        
        # Your test logic here
        assert "AdCP Sales Agent Admin" in await authenticated_page.content()
        
        # Navigate to create tenant
        await authenticated_page.click('a:has-text("Create Tenant")')
        assert "Create New Tenant" in await authenticated_page.content()