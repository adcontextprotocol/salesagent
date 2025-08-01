"""Basic tests to verify UI testing setup."""

import pytest
from playwright.async_api import Page

class TestBasicSetup:
    """Basic tests to verify the UI testing framework is working."""
    
    @pytest.mark.asyncio
    async def test_browser_launches(self, page: Page):
        """Test that browser launches successfully."""
        assert page is not None
        assert await page.evaluate("() => true") is True
    
    @pytest.mark.asyncio
    async def test_can_navigate_to_base_url(self, page: Page, base_url: str):
        """Test navigation to base URL."""
        await page.goto(base_url)
        
        # Check we got a response
        assert page.url is not None
        
        # Should either show login page or main admin page if already logged in
        content = await page.content()
        assert ("/login" in page.url or "Login" in content or 
                "AdCP Sales Agent Admin" in content)
    
    @pytest.mark.asyncio
    async def test_page_has_title(self, page: Page, base_url: str):
        """Test that page has a title."""
        await page.goto(base_url)
        
        title = await page.title()
        assert title is not None
        assert len(title) > 0
    
    @pytest.mark.asyncio
    async def test_screenshot_capability(self, page: Page, base_url: str):
        """Test screenshot functionality."""
        await page.goto(base_url)
        
        # Take a screenshot
        screenshot_path = "screenshots/test_screenshot.png"
        await page.screenshot(path=screenshot_path)
        
        # Verify screenshot was taken
        import os
        assert os.path.exists(screenshot_path)
    
    @pytest.mark.asyncio
    async def test_login_page_elements(self, page: Page, base_url: str):
        """Test that login page has expected elements."""
        # Navigate to login directly
        await page.goto(f"{base_url}/login")
        
        # Wait for page to load
        await page.wait_for_load_state("networkidle")
        
        # Check current state - might be logged in or show login page
        content = await page.content()
        
        if "logout" in content.lower():
            # Already logged in, check for logout functionality
            assert "AdCP Sales Agent Admin" in content
            logout_link = await page.query_selector('a[href="/logout"]')
            assert logout_link is not None
        else:
            # Should be on login page
            assert "login" in content.lower() or "sign in" in content.lower()
            
            # Check for Google OAuth button if it exists
            google_button = await page.query_selector('a:has-text("Login with Google")')
            if google_button:
                assert await google_button.is_visible()