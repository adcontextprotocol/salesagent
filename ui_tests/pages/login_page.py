from .base_page import BasePage
from playwright.async_api import Page

class LoginPage(BasePage):
    """Login page object model."""
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        
        # Selectors
        self.google_login_button = 'a:has-text("Login with Google")'
        self.email_input = 'input[type="email"]'
        self.password_input = 'input[type="password"]' 
        self.submit_button = 'button[type="submit"]'
        self.error_message = '.error-message'
        self.user_menu = '.user-menu'
        
    async def goto_login(self) -> None:
        """Navigate to login page."""
        await self.navigate_to("/login")
    
    async def click_google_login(self) -> None:
        """Click Google login button."""
        await self.click(self.google_login_button)
    
    async def login_with_credentials(self, email: str, password: str) -> None:
        """Login with email and password (if available)."""
        await self.fill(self.email_input, email)
        await self.fill(self.password_input, password)
        await self.click(self.submit_button)
    
    async def is_logged_in(self) -> bool:
        """Check if user is logged in."""
        try:
            await self.wait_for_element(self.user_menu, state="visible")
            return True
        except:
            return False
    
    async def get_error_message(self) -> str:
        """Get login error message."""
        if await self.is_visible(self.error_message):
            return await self.get_text(self.error_message)
        return ""
    
    async def wait_for_redirect_after_login(self) -> None:
        """Wait for redirect after successful login."""
        await self.page.wait_for_url("**/", timeout=10000)