import pytest
from playwright.async_api import Page
from ..pages.login_page import LoginPage
from ..utils.auth_helper import AuthHelper
from ..utils.test_data import TestConstants

class TestAuthentication:
    """Test authentication flows."""
    
    @pytest.mark.asyncio
    async def test_google_oauth_login(self, page: Page, base_url: str):
        """Test Google OAuth login flow."""
        login_page = LoginPage(page, base_url)
        
        # Navigate to login page
        await login_page.goto_login()
        
        # Verify login page loaded
        assert await login_page.is_visible(login_page.google_login_button)
        
        # Attempt Google OAuth login
        success = await AuthHelper.login_with_google_oauth(page, "test@example.com")
        
        # Verify login success
        assert success
        assert await login_page.is_logged_in()
        
        # Verify redirect to home page
        assert "/login" not in await page.url
    
    @pytest.mark.asyncio
    async def test_logout(self, page: Page, base_url: str):
        """Test logout functionality."""
        # First login
        await AuthHelper.login_as_regular_user(page, base_url)
        
        # Verify logged in
        assert await AuthHelper.is_authenticated(page)
        
        # Logout
        await AuthHelper.logout(page)
        
        # Verify logged out
        assert not await AuthHelper.is_authenticated(page)
        assert "/login" in await page.url
    
    @pytest.mark.asyncio
    async def test_admin_access(self, page: Page, base_url: str):
        """Test admin user access."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        # Navigate to admin-only page
        await page.goto(f"{base_url}/tenants")
        
        # Verify access granted
        assert "Access Denied" not in await page.content()
        assert await page.is_visible('a:has-text("Create New Tenant")')
    
    @pytest.mark.asyncio
    async def test_regular_user_restrictions(self, page: Page, base_url: str):
        """Test regular user access restrictions."""
        # Login as regular user
        await AuthHelper.login_as_regular_user(page, base_url)
        
        # Try to access admin page
        await page.goto(f"{base_url}/create_tenant")
        
        # Verify access denied or redirect
        content = await page.content()
        assert ("Access Denied" in content or 
                "Permission denied" in content or
                "/login" in await page.url)
    
    @pytest.mark.asyncio
    async def test_session_persistence(self, page: Page, context, base_url: str):
        """Test session persistence across page reloads."""
        # Login
        await AuthHelper.login_as_regular_user(page, base_url)
        assert await AuthHelper.is_authenticated(page)
        
        # Reload page
        await page.reload()
        
        # Verify still authenticated
        assert await AuthHelper.is_authenticated(page)
        
        # Open new page in same context
        new_page = await context.new_page()
        await new_page.goto(base_url)
        
        # Verify authenticated in new page
        assert await AuthHelper.is_authenticated(new_page)
        
        await new_page.close()
    
    @pytest.mark.asyncio
    async def test_invalid_credentials(self, page: Page, base_url: str):
        """Test login with invalid credentials."""
        login_page = LoginPage(page, base_url)
        
        # Navigate to login page
        await login_page.goto_login()
        
        # If there's a traditional login form (not just OAuth)
        if await login_page.is_visible(login_page.email_input):
            # Try invalid credentials
            await login_page.login_with_credentials(
                "invalid@example.com", 
                "wrongpassword"
            )
            
            # Verify error message
            error_msg = await login_page.get_error_message()
            assert error_msg != ""
            assert not await login_page.is_logged_in()