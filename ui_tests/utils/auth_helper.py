from playwright.async_api import Page, BrowserContext
import os
import json
from typing import Optional, Dict

class AuthHelper:
    """Helper class for authentication in tests."""
    
    @staticmethod
    async def ensure_logged_out(page: Page, base_url: str) -> None:
        """Ensure user is logged out before attempting login."""
        await page.goto(base_url)
        
        # Check if logged in by looking for logout link
        logout_link = await page.query_selector('a[href="/logout"]')
        if logout_link:
            print("User is logged in, logging out...")
            await page.click('a[href="/logout"]')
            await page.wait_for_load_state("networkidle")
            # The app might auto-login again, so we need to check
            await page.wait_for_timeout(1000)
    
    @staticmethod
    async def login_with_google_oauth(page: Page, email: str, password: str = None) -> bool:
        """
        Handle Google OAuth login flow.
        
        Note: This requires either:
        1. Real Google credentials and handling actual OAuth flow
        2. A test OAuth provider
        3. Session manipulation (if app supports it)
        """
        try:
            # First ensure we're logged out
            await AuthHelper.ensure_logged_out(page, page.url.split('/')[0] + '//' + page.url.split('/')[2])
            
            # Navigate to login page
            current_url = page.url
            if "/login" not in current_url:
                await page.goto("/login")
                await page.wait_for_load_state("networkidle")
            
            # Look for Google login button
            google_button = await page.query_selector('a:has-text("Login with Google")')
            if not google_button:
                print("No Google login button found")
                return False
            
            # Click Google login button
            # This will open Google's OAuth page
            async with page.context.expect_page() as new_page_info:
                await google_button.click()
                oauth_page = await new_page_info.value
            
            # Handle Google OAuth flow
            # This is where you'd enter credentials on Google's page
            # For now, we'll just close the popup as we can't automate real Google login
            await oauth_page.close()
            
            print("Note: Real Google OAuth cannot be automated without violating Google's ToS")
            print("Consider using one of these alternatives:")
            print("1. Add a test mode to the application")
            print("2. Use session pre-configuration")
            print("3. Mock the OAuth provider")
            
            return False
        except Exception as e:
            print(f"Login failed: {e}")
            return False
    
    @staticmethod
    async def setup_auth_state(context: BrowserContext, auth_token: str, 
                              user_data: Dict[str, any]) -> None:
        """Set up authentication state in browser context."""
        # Add auth cookies or local storage
        await context.add_cookies([{
            'name': 'session',
            'value': auth_token,
            'domain': 'localhost',
            'path': '/',
            'httpOnly': True,
            'secure': False,
            'sameSite': 'Lax'
        }])
        
        # Store user data in local storage if needed
        await context.add_init_script(f"""
            window.localStorage.setItem('user', JSON.stringify({json.dumps(user_data)}));
        """)
    
    @staticmethod
    async def is_authenticated(page: Page) -> bool:
        """Check if user is authenticated."""
        try:
            # Check for user menu or logout button
            await page.wait_for_selector('.user-menu', timeout=5000)
            return True
        except:
            return False
    
    @staticmethod
    async def logout(page: Page) -> None:
        """Logout from the application."""
        # Click user menu
        await page.click('.user-menu')
        
        # Click logout
        await page.click('a:has-text("Logout")')
        
        # Wait for redirect to login
        await page.wait_for_url("**/login")
    
    @staticmethod
    def get_test_auth_token() -> Optional[str]:
        """Get test authentication token from environment."""
        return os.getenv("TEST_AUTH_TOKEN")
    
    @staticmethod
    async def login_with_session_cookie(page: Page, base_url: str, email: str, 
                                       role: str = "super_admin") -> bool:
        """
        Login by setting session cookie directly.
        This bypasses OAuth for testing purposes.
        
        Note: This requires knowing the Flask session secret key or
        having a test endpoint that sets the session.
        """
        # Navigate to the site first to get the domain
        await page.goto(base_url)
        
        # Option 1: If we had a test endpoint (recommended to add to admin_ui.py)
        test_auth_url = f"{base_url}/test/auth/login"
        try:
            response = await page.request.post(test_auth_url, data={
                "email": email,
                "role": role,
                "username": email.split('@')[0]
            })
            if response.ok:
                await page.goto(base_url)
                return True
        except:
            pass
        
        # Option 2: Try to use the existing session if already logged in
        # This works if the container has persistent sessions
        content = await page.content()
        if email in content and "logout" in content.lower():
            print(f"Already logged in as {email}")
            return True
        
        print("Session-based login not available. Add TEST_MODE support to admin_ui.py")
        return False
    
    @staticmethod
    async def login_as_admin(page: Page, base_url: str) -> bool:
        """Login as admin user."""
        admin_email = os.getenv("TEST_ADMIN_EMAIL", "admin@example.com")
        # Try session-based login first, fall back to OAuth
        if await AuthHelper.login_with_session_cookie(page, base_url, admin_email, "super_admin"):
            return True
        return await AuthHelper.login_with_google_oauth(page, admin_email)
    
    @staticmethod
    async def login_as_regular_user(page: Page, base_url: str) -> bool:
        """Login as regular user."""
        user_email = os.getenv("TEST_USER_EMAIL", "user@example.com")
        # Try session-based login first, fall back to OAuth
        if await AuthHelper.login_with_session_cookie(page, base_url, user_email, "viewer"):
            return True
        return await AuthHelper.login_with_google_oauth(page, user_email)