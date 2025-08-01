#!/usr/bin/env python3
"""Save authentication state from current browser session."""
import asyncio
from playwright.async_api import async_playwright
import json

async def save_auth():
    """Save current authentication state."""
    async with async_playwright() as p:
        # Launch browser in non-headless mode
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate to admin UI
        await page.goto("http://localhost:8002")
        
        print("Please login manually in the browser window that just opened.")
        print("Once logged in, press Enter here to save the authentication state...")
        input()
        
        # Save the storage state
        await context.storage_state(path="test_auth_state.json")
        print("✅ Authentication state saved to test_auth_state.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(save_auth())