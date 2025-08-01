"""Explore login page to understand the flow."""

import pytest
from playwright.async_api import Page
import os

class TestExploreLogin:
    @pytest.mark.asyncio
    async def test_explore_login_flow(self, page: Page, base_url: str):
        """Explore the login flow."""
        # First, let's logout if we're logged in
        await page.goto(base_url)
        
        # Check if we're logged in
        if "logout" in (await page.content()).lower():
            print("Currently logged in, logging out...")
            await page.click('a[href="/logout"]')
            await page.wait_for_load_state("networkidle")
        
        # Now we should be on login page
        print(f"Current URL: {page.url}")
        
        # Take screenshot of login page
        os.makedirs("screenshots", exist_ok=True)
        await page.screenshot(path="screenshots/login_page.png")
        
        # Look for login elements
        content = await page.content()
        
        # Check for Google OAuth
        google_button = await page.query_selector('a:has-text("Login with Google")')
        if google_button:
            print("Found Google OAuth button")
            href = await google_button.get_attribute("href")
            print(f"OAuth URL: {href}")
        
        # Check for email/password form
        email_input = await page.query_selector('input[type="email"]')
        password_input = await page.query_selector('input[type="password"]')
        
        if email_input and password_input:
            print("Found email/password form")
        else:
            print("No traditional login form found, only OAuth")
            
        # Save the page HTML for inspection
        with open("screenshots/login_page.html", "w") as f:
            f.write(content)