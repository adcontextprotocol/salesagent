from playwright.async_api import Page, Locator
from typing import Optional, Union
import asyncio

class BasePage:
    """Base page class with common functionality."""
    
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.timeout = 30000  # 30 seconds default timeout
    
    async def navigate_to(self, path: str = "") -> None:
        """Navigate to a specific path."""
        url = f"{self.base_url}{path}"
        await self.page.goto(url)
        await self.wait_for_load()
    
    async def wait_for_load(self) -> None:
        """Wait for page to load."""
        await self.page.wait_for_load_state("networkidle")
    
    async def get_element(self, selector: str) -> Locator:
        """Get element by selector."""
        return self.page.locator(selector)
    
    async def click(self, selector: str) -> None:
        """Click an element."""
        await self.page.click(selector)
    
    async def fill(self, selector: str, text: str) -> None:
        """Fill input field."""
        await self.page.fill(selector, text)
    
    async def select_option(self, selector: str, value: Union[str, list]) -> None:
        """Select option from dropdown."""
        await self.page.select_option(selector, value)
    
    async def wait_for_element(self, selector: str, state: str = "visible") -> Locator:
        """Wait for element to be in specific state."""
        locator = self.page.locator(selector)
        if state == "visible":
            await locator.wait_for(state="visible", timeout=self.timeout)
        elif state == "hidden":
            await locator.wait_for(state="hidden", timeout=self.timeout)
        elif state == "attached":
            await locator.wait_for(state="attached", timeout=self.timeout)
        return locator
    
    async def is_visible(self, selector: str) -> bool:
        """Check if element is visible."""
        return await self.page.is_visible(selector)
    
    async def get_text(self, selector: str) -> str:
        """Get text content of element."""
        return await self.page.text_content(selector)
    
    async def screenshot(self, path: str) -> None:
        """Take screenshot of current page."""
        await self.page.screenshot(path=path)
    
    async def wait_for_url(self, url_pattern: str) -> None:
        """Wait for URL to match pattern."""
        await self.page.wait_for_url(url_pattern)
    
    async def get_current_url(self) -> str:
        """Get current URL."""
        return self.page.url
    
    async def reload(self) -> None:
        """Reload the page."""
        await self.page.reload()
    
    async def wait_for_response(self, url_pattern: str) -> None:
        """Wait for specific API response."""
        await self.page.wait_for_response(url_pattern)
    
    async def evaluate_script(self, script: str) -> any:
        """Execute JavaScript in page context."""
        return await self.page.evaluate(script)