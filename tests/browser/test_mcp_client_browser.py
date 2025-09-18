"""
Browser-based testing for MCP client integration in landing pages.

This test suite validates that the MCP client loads and functions properly
in real browsers without manual debugging cycles.
"""

import asyncio
import logging
from typing import Any

import pytest
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class MCPClientBrowserTester:
    """Comprehensive browser testing for MCP client integration."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.test_results: dict[str, Any] = {}

    async def test_mcp_client_loading(self, page: Page) -> dict[str, Any]:
        """Test that MCP client loads without dependency errors."""
        console_messages = []
        errors = []

        # Capture console messages and errors
        page.on(
            "console",
            lambda msg: console_messages.append({"type": msg.type, "text": msg.text, "location": msg.location}),
        )

        page.on(
            "pageerror", lambda error: errors.append({"message": str(error), "stack": getattr(error, "stack", None)})
        )

        # Navigate to landing page
        await page.goto(f"{self.base_url}/")

        # Wait for page to load
        await page.wait_for_load_state("networkidle")

        # Check for dependency resolution errors
        ajv_errors = [msg for msg in console_messages if "ajv" in msg["text"].lower()]
        module_errors = [msg for msg in console_messages if "does not resolve to a valid url" in msg["text"].lower()]

        # Check if searchProducts function is available
        search_function_available = await page.evaluate("typeof window.searchProducts === 'function'")

        return {
            "ajv_errors": ajv_errors,
            "module_errors": module_errors,
            "search_function_available": search_function_available,
            "console_messages": console_messages,
            "page_errors": errors,
            "total_errors": len([msg for msg in console_messages if msg["type"] == "error"]) + len(errors),
        }

    async def test_mcp_client_functionality(self, page: Page) -> dict[str, Any]:
        """Test that MCP client can successfully make API calls."""

        # Navigate to landing page
        await page.goto(f"{self.base_url}/")
        await page.wait_for_load_state("networkidle")

        # Fill in test brief
        await page.fill("#briefInput", "display ads for technology content")

        # Capture network requests
        responses = []
        page.on(
            "response",
            lambda response: responses.append(
                {"url": response.url, "status": response.status, "headers": dict(response.headers)}
            ),
        )

        # Click search button
        await page.click(".search-btn")

        # Wait for results or error
        await page.wait_for_timeout(3000)  # Give time for API call

        # Check results
        results_element = page.locator("#results")
        results_content = await results_element.inner_html()

        # Check for error messages
        has_error = "error" in results_content.lower() or "sorry" in results_content.lower()
        has_products = "product-card" in results_content

        return {
            "results_content": results_content,
            "has_error": has_error,
            "has_products": has_products,
            "network_responses": responses,
            "mcp_requests": [r for r in responses if "/mcp" in r["url"]],
        }

    async def test_alternative_implementations(self, page: Page) -> dict[str, Any]:
        """Test alternative MCP client loading strategies."""

        strategies_tested = []

        # Strategy 1: Direct fetch approach (bypass MCP SDK)
        await page.goto(f"{self.base_url}/")

        direct_fetch_result = await page.evaluate(
            """
            async () => {
                try {
                    const response = await fetch('/mcp', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-adcp-auth': 'demo_token'
                        },
                        body: JSON.stringify({
                            jsonrpc: '2.0',
                            id: 1,
                            method: 'tools/call',
                            params: {
                                name: 'get_products',
                                arguments: {
                                    brief: 'test content'
                                }
                            }
                        })
                    });
                    return {
                        status: response.status,
                        success: response.ok,
                        headers: Object.fromEntries(response.headers.entries())
                    };
                } catch (error) {
                    return {
                        error: error.message,
                        success: false
                    };
                }
            }
        """
        )

        strategies_tested.append({"name": "direct_fetch", "result": direct_fetch_result})

        return {"strategies": strategies_tested}


@pytest.mark.browser
class TestMCPClientBrowser:
    """Browser test cases for MCP client integration."""

    @pytest.fixture
    async def tester(self):
        """Create MCP client browser tester."""
        return MCPClientBrowserTester()

    @pytest.mark.asyncio
    async def test_mcp_client_loads_without_errors(self, page: Page, tester: MCPClientBrowserTester):
        """Test that MCP client loads without dependency resolution errors."""

        result = await tester.test_mcp_client_loading(page)

        # Should not have AJV errors
        assert len(result["ajv_errors"]) == 0, f"AJV dependency errors found: {result['ajv_errors']}"

        # Should not have module resolution errors
        assert len(result["module_errors"]) == 0, f"Module resolution errors: {result['module_errors']}"

        # Should have searchProducts function available
        assert result["search_function_available"], "searchProducts function not available globally"

        # Should have minimal errors overall
        assert result["total_errors"] <= 1, f"Too many errors ({result['total_errors']}): {result['console_messages']}"

    @pytest.mark.asyncio
    async def test_mcp_client_api_calls_work(self, page: Page, tester: MCPClientBrowserTester):
        """Test that MCP client can successfully make API calls."""

        result = await tester.test_mcp_client_functionality(page)

        # Should not have error messages in results
        assert not result["has_error"], f"Error in results: {result['results_content']}"

        # Should have made MCP requests
        assert len(result["mcp_requests"]) > 0, "No MCP requests were made"

        # MCP requests should return success status
        successful_requests = [r for r in result["mcp_requests"] if 200 <= r["status"] < 300]
        assert len(successful_requests) > 0, f"No successful MCP requests: {result['mcp_requests']}"

    @pytest.mark.asyncio
    async def test_fallback_approaches_work(self, page: Page, tester: MCPClientBrowserTester):
        """Test that fallback approaches work when MCP SDK fails."""

        result = await tester.test_alternative_implementations(page)

        # Direct fetch should work
        direct_fetch = next((s for s in result["strategies"] if s["name"] == "direct_fetch"), None)
        assert direct_fetch is not None, "Direct fetch strategy not tested"

        fetch_result = direct_fetch["result"]
        assert fetch_result.get("success", False), f"Direct fetch failed: {fetch_result}"


@pytest.mark.browser
@pytest.mark.skip_ci
async def test_mcp_client_comprehensive_debugging():
    """Comprehensive debugging test that can be run manually."""

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Test in multiple browsers
        browsers = [("chromium", p.chromium), ("firefox", p.firefox), ("webkit", p.webkit)]

        results = {}

        for browser_name, browser_type in browsers:
            try:
                browser = await browser_type.launch(headless=False)  # Visible for debugging
                page = await browser.new_page()

                tester = MCPClientBrowserTester()

                # Run all tests
                loading_result = await tester.test_mcp_client_loading(page)
                functionality_result = await tester.test_mcp_client_functionality(page)
                alternatives_result = await tester.test_alternative_implementations(page)

                results[browser_name] = {
                    "loading": loading_result,
                    "functionality": functionality_result,
                    "alternatives": alternatives_result,
                }

                await browser.close()

            except Exception as e:
                results[browser_name] = {"error": str(e)}

        # Print comprehensive results
        print("\n=== MCP Client Browser Test Results ===")
        for browser_name, result in results.items():
            print(f"\n{browser_name.upper()}:")
            if "error" in result:
                print(f"  ❌ Failed to test: {result['error']}")
            else:
                loading = result["loading"]
                print(
                    f"  Loading: {len(loading['ajv_errors'])} AJV errors, {len(loading['module_errors'])} module errors"
                )
                print(f"  Function available: {loading['search_function_available']}")
                print(f"  Total errors: {loading['total_errors']}")

                if result["functionality"]["has_products"]:
                    print("  ✅ API calls working")
                elif result["functionality"]["has_error"]:
                    print("  ❌ API calls failing")
                else:
                    print("  ⚠️  API calls unclear")

        return results


if __name__ == "__main__":
    # Run the comprehensive debugging test
    asyncio.run(test_mcp_client_comprehensive_debugging())
