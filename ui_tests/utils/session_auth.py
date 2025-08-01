"""
Session-based authentication for UI tests.
This module provides methods to authenticate by manipulating browser storage/cookies.
"""

import base64
import json
from typing import Dict, Optional
from playwright.async_api import Page, BrowserContext

class SessionAuth:
    """Handle session-based authentication for testing."""
    
    @staticmethod
    async def check_current_auth(page: Page) -> Dict[str, any]:
        """Check current authentication status."""
        # Get the base URL from current page or use default
        current_url = page.url
        if current_url and current_url.startswith("http"):
            base_url = '/'.join(current_url.split('/')[:3])  # Extract protocol://host:port
            await page.goto(base_url)
        else:
            # If no valid URL, navigate to default
            await page.goto("http://localhost:8001")
        content = await page.content()
        
        # Look for indicators of being logged in
        is_logged_in = "logout" in content.lower()
        email = None
        role = None
        
        if is_logged_in:
            # Try to extract email from the page
            # Look for pattern like "dev@example.com"
            import re
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
            if email_match:
                email = email_match.group(1)
            
            # Check for role indicators
            if "Super Admin" in content:
                role = "super_admin"
            elif "Admin" in content:
                role = "admin"
            else:
                role = "viewer"
        
        return {
            "logged_in": is_logged_in,
            "email": email,
            "role": role
        }
    
    @staticmethod
    async def force_logout(page: Page, base_url: str) -> bool:
        """Force logout by clearing all cookies and storage."""
        # Clear all cookies
        await page.context.clear_cookies()
        
        # Clear local storage
        await page.goto(base_url)
        await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        
        # Try clicking logout if available
        try:
            await page.click('a[href="/logout"]', timeout=2000)
            await page.wait_for_load_state("networkidle")
        except:
            pass
        
        # Verify logged out
        auth_status = await SessionAuth.check_current_auth(page)
        return not auth_status["logged_in"]
    
    @staticmethod
    async def login_with_credentials(page: Page, base_url: str, 
                                   email: str, password: str) -> bool:
        """
        Attempt to login with email/password.
        
        Since this app uses Google OAuth only, this method will:
        1. Check if already logged in with the right email
        2. Provide instructions for setting up test authentication
        """
        # Check current auth status
        current_auth = await SessionAuth.check_current_auth(page)
        
        if current_auth["logged_in"] and current_auth["email"] == email:
            print(f"Already logged in as {email}")
            return True
        
        # Since we can't automate Google OAuth, provide alternatives
        print("\n" + "="*60)
        print("AUTHENTICATION OPTIONS FOR UI TESTING")
        print("="*60)
        print("\nThis application uses Google OAuth exclusively.")
        print("To enable automated testing with credentials, you have these options:")
        print("\n1. **Use Existing Session** (Recommended for local testing)")
        print("   - Manually login once via browser")
        print("   - Keep the container running")
        print("   - Tests will use the existing session")
        print("\n2. **Add Test Authentication** (Recommended for CI/CD)")
        print("   - Run: python ui_tests/add_test_auth.py")
        print("   - Set: ENABLE_TEST_AUTH=true")
        print("   - Restart the admin UI server")
        print("\n3. **Mock OAuth Provider**")
        print("   - Set up a local OAuth mock server")
        print("   - Configure Google OAuth to use it")
        print("\n4. **Pre-configure Browser Context**")
        print("   - Save authentication state after manual login")
        print("   - Load state in test setup")
        print("="*60 + "\n")
        
        return False
    
    @staticmethod
    async def save_auth_state(page: Page, filepath: str) -> None:
        """Save current authentication state to file."""
        # This saves cookies and local storage
        await page.context.storage_state(path=filepath)
        print(f"Saved authentication state to {filepath}")
    
    @staticmethod
    async def load_auth_state(context: BrowserContext, filepath: str) -> bool:
        """Load authentication state from file."""
        import os
        if not os.path.exists(filepath):
            print(f"Auth state file not found: {filepath}")
            return False
        
        # This would be done when creating the context
        # For existing context, we need to manually add cookies
        with open(filepath, 'r') as f:
            state = json.load(f)
        
        # Add cookies
        if 'cookies' in state:
            await context.add_cookies(state['cookies'])
        
        return True