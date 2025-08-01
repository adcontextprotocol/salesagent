import pytest
import pytest_asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Dict, AsyncGenerator
import os
from dotenv import load_dotenv

load_dotenv()

@pytest_asyncio.fixture(scope="function")
async def browser() -> AsyncGenerator[Browser, None]:
    """Launch browser instance for the session."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            args=["--disable-blink-features=AutomationControlled"]
        )
        yield browser
        await browser.close()

@pytest_asyncio.fixture(scope="function")
async def context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """Create a new browser context for each test."""
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )
    
    # Enable request/response logging if debug mode
    if os.getenv("DEBUG", "false").lower() == "true":
        context.on("request", lambda request: print(f">> {request.method} {request.url}"))
        context.on("response", lambda response: print(f"<< {response.status} {response.url}"))
    
    yield context
    await context.close()

@pytest_asyncio.fixture(scope="function")
async def page(context: BrowserContext) -> AsyncGenerator[Page, None]:
    """Create a new page for each test."""
    page = await context.new_page()
    yield page
    await page.close()

@pytest.fixture(scope="session")
def base_url() -> str:
    """Get base URL for the application."""
    return os.getenv("BASE_URL", "http://localhost:8001")

@pytest.fixture(scope="session")
def test_credentials() -> Dict[str, str]:
    """Get test credentials."""
    return {
        "email": os.getenv("TEST_USER_EMAIL", "test@example.com"),
        "password": os.getenv("TEST_USER_PASSWORD", "testpass123"),
        "admin_email": os.getenv("TEST_ADMIN_EMAIL", "admin@example.com"),
        "admin_password": os.getenv("TEST_ADMIN_PASSWORD", "adminpass123")
    }

@pytest.fixture(autouse=True)
async def screenshot_on_failure(request, page: Page):
    """Take screenshot on test failure."""
    yield
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        screenshot_path = f"screenshots/{request.node.name}.png"
        os.makedirs("screenshots", exist_ok=True)
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot saved: {screenshot_path}")

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Make test result available to fixtures."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)