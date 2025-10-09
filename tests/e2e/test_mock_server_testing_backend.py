"""
Mock server testing backend implementation test suite.

This test validates the mock server's AdCP testing hooks, time simulation, event jumping,
error scenarios, and production isolation features as defined in the AdCP testing specification.
"""

import json
import uuid

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


class TestMockServerTestingBackend:
    """Test suite for mock server AdCP testing backend features."""

    @pytest.mark.asyncio
    async def test_debug_mode_information(self, live_server, test_auth_token):
        """Test that debug mode provides comprehensive testing information."""
        headers = {
            "x-adcp-auth": test_auth_token,
            "X-Dry-Run": "true",
            "X-Test-Session-ID": f"debug_test_{uuid.uuid4().hex[:8]}",
            "X-Debug-Mode": "true",
            "X-Jump-To-Event": "campaign-midpoint",
            "X-Mock-Time": "2025-10-15T12:00:00Z",
        }

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Test debug info in products endpoint
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "debug test", "promoted_offering": "debug products"}}
            )
            products = json.loads(products_result.content[0].text)

            # Should contain debug information
            debug_info_found = (
                "debug_info" in products
                or products.get("is_test")
                or any("debug" in str(v).lower() for v in products.values() if isinstance(v, str))
            )

            assert debug_info_found, "Debug mode should provide debug information"

            print("✓ Debug mode: comprehensive information provided")
            print(f"  - Response keys: {list(products.keys())}")
            print(f"  - Contains test markers: {products.get('is_test', False)}")
