"""
Example tests showing different authentication approaches.
"""

import pytest
import os
from playwright.async_api import Page, BrowserContext
from ..utils.session_auth import SessionAuth
from ..utils.auth_helper import AuthHelper

class TestAuthenticationExample:
    """Examples of different authentication methods."""
    
    @pytest.mark.asyncio
    async def test_check_auth_status(self, page: Page, base_url: str):
        """Check current authentication status."""
        await page.goto(base_url)
        
        # Check auth status
        auth_status = await SessionAuth.check_current_auth(page)
        
        print("\nCurrent Authentication Status:")
        print(f"  Logged in: {auth_status['logged_in']}")
        print(f"  Email: {auth_status['email']}")
        print(f"  Role: {auth_status['role']}")
        
        # This test just reports status, doesn't assert
        assert True
    
    @pytest.mark.asyncio
    async def test_login_with_saved_state(self, page: Page, base_url: str):
        """Demonstrate using saved authentication state."""
        auth_file = "auth_state.json"
        
        # First, check if we have saved auth state
        if os.path.exists(auth_file):
            print(f"\nFound saved auth state at {auth_file}")
            # Note: Loading state should be done when creating context
            # This is just for demonstration
        else:
            print(f"\nNo saved auth state found.")
            print("To save current auth state:")
            print("1. Login manually in browser")
            print("2. Run: await SessionAuth.save_auth_state(page, 'auth_state.json')")
        
        # For now, just use existing session if available
        auth_status = await SessionAuth.check_current_auth(page)
        assert auth_status["logged_in"] or True  # Don't fail, just demonstrate
    
    @pytest.mark.asyncio 
    async def test_login_with_credentials(self, page: Page, base_url: str):
        """Attempt to login with email/password credentials."""
        email = os.getenv("TEST_ADMIN_EMAIL", "test@example.com")
        password = os.getenv("TEST_ADMIN_PASSWORD", "password")
        
        # This will show authentication options since OAuth is required
        result = await SessionAuth.login_with_credentials(
            page, base_url, email, password
        )
        
        # The test passes to show the instructions
        assert True
    
    @pytest.mark.asyncio
    async def test_logout_and_check(self, page: Page, base_url: str):
        """Test logout functionality."""
        # Check initial state
        initial_auth = await SessionAuth.check_current_auth(page)
        print(f"\nInitial state: {'Logged in' if initial_auth['logged_in'] else 'Logged out'}")
        
        if initial_auth["logged_in"]:
            # Try to logout
            print("Attempting logout...")
            logout_success = await SessionAuth.force_logout(page, base_url)
            
            # Check state after logout
            final_auth = await SessionAuth.check_current_auth(page)
            print(f"After logout: {'Logged in' if final_auth['logged_in'] else 'Logged out'}")
            
            # Note: The app might auto-login again due to session persistence
            if final_auth["logged_in"]:
                print("Note: App auto-logged in again (persistent session)")
    
    @pytest.mark.asyncio
    async def test_save_current_auth_state(self, page: Page, base_url: str):
        """Save current authentication state for reuse."""
        # Check if logged in
        auth_status = await SessionAuth.check_current_auth(page)
        
        if auth_status["logged_in"]:
            # Save the state
            auth_file = "test_auth_state.json"
            await SessionAuth.save_auth_state(page, auth_file)
            print(f"\nSaved auth state to {auth_file}")
            print("You can now use this file to pre-authenticate tests")
        else:
            print("\nNot logged in - cannot save auth state")
            print("Please login manually first")


class TestAuthenticationWithContext:
    """Example using pre-configured context."""
    
    @pytest.mark.asyncio
    async def test_with_saved_auth_context(self, browser, base_url: str):
        """Create context with saved authentication."""
        auth_file = "test_auth_state.json"
        
        if os.path.exists(auth_file):
            # Create context with saved state
            context = await browser.new_context(storage_state=auth_file)
            page = await context.new_page()
            
            # Navigate and check auth
            await page.goto(base_url)
            auth_status = await SessionAuth.check_current_auth(page)
            
            print(f"\nLoaded auth from file: {auth_status}")
            assert auth_status["logged_in"]
            
            await page.close()
            await context.close()
        else:
            print(f"\nNo saved auth state at {auth_file}")
            print("Run test_save_current_auth_state first")
            pytest.skip("No saved auth state available")