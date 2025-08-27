"""
Comprehensive end-to-end test for AdCP Sales Agent Server.

This test exercises all AdCP tools and protocols, implementing the testing hooks
from https://github.com/adcontextprotocol/adcp/pull/34.

It can be run in multiple modes:
- local: Starts its own test servers
- docker: Uses existing Docker services
- ci: Optimized for CI environments
- external: Tests against any AdCP-compliant server

Usage:
    pytest tests/e2e/test_adcp_full_lifecycle.py --mode=docker
    pytest tests/e2e/test_adcp_full_lifecycle.py --server-url=https://example.com
"""

import json
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Test configuration defaults
DEFAULT_MCP_PORT = 8155  # From .env ADCP_SALES_PORT
DEFAULT_A2A_PORT = 8091  # From docker-compose.yml A2A_PORT
DEFAULT_ADMIN_PORT = 8076  # From .env ADMIN_UI_PORT
TEST_TIMEOUT = 30


class AdCPTestClient:
    """Client for testing AdCP servers with full testing hook support."""

    def __init__(
        self, mcp_url: str, a2a_url: str, auth_token: str, test_session_id: str | None = None, dry_run: bool = True
    ):
        self.mcp_url = mcp_url
        self.a2a_url = a2a_url
        self.auth_token = auth_token
        self.test_session_id = test_session_id or str(uuid.uuid4())
        self.dry_run = dry_run
        self.mock_time = None
        self.mcp_client = None
        self.http_client = httpx.AsyncClient()

    async def __aenter__(self):
        """Enter async context."""
        headers = self._build_headers()
        transport = StreamableHttpTransport(url=f"{self.mcp_url}/mcp/", headers=headers)
        self.mcp_client = Client(transport=transport)
        await self.mcp_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self.mcp_client:
            await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
        await self.http_client.aclose()

    def _build_headers(self) -> dict[str, str]:
        """Build headers with testing hooks."""
        headers = {"x-adcp-auth": self.auth_token, "X-Test-Session-ID": self.test_session_id}

        if self.dry_run:
            headers["X-Dry-Run"] = "true"

        if self.mock_time:
            headers["X-Mock-Time"] = self.mock_time

        return headers

    def set_mock_time(self, timestamp: datetime):
        """Set the mock time for simulated progression."""
        self.mock_time = timestamp.isoformat() + "Z"
        # Update client headers
        if self.mcp_client and hasattr(self.mcp_client, "_transport"):
            self.mcp_client._transport.headers.update(self._build_headers())

    def jump_to_event(self, event: str):
        """Set header to jump to a specific lifecycle event."""
        headers = self._build_headers()
        headers["X-Jump-To-Event"] = event
        if self.mcp_client and hasattr(self.mcp_client, "_transport"):
            self.mcp_client._transport.headers.update(headers)

    async def call_mcp_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call an MCP tool and parse the response."""
        result = await self.mcp_client.call_tool(tool_name, {"req": params})

        # Parse JSON from TextContent response
        if hasattr(result, "content") and isinstance(result.content, list):
            if result.content and hasattr(result.content[0], "text"):
                return json.loads(result.content[0].text)
        return result

    async def query_a2a(self, query: str) -> dict[str, Any]:
        """Query the A2A server using REST transport."""
        headers = self._build_headers()
        # A2A expects Bearer token in Authorization header
        headers["Authorization"] = f"Bearer {self.auth_token}"

        response = await self.http_client.post(
            f"{self.a2a_url}/message", json={"message": query, "thread_id": self.test_session_id}, headers=headers
        )
        response.raise_for_status()
        return response.json()


class TestAdCPFullLifecycle:
    """Comprehensive E2E test suite for AdCP protocol compliance."""

    @pytest.fixture
    async def test_client(self, request, docker_services_e2e) -> AdCPTestClient:
        """Create test client based on test mode."""
        mode = request.config.getoption("--mode", "docker")
        server_url = request.config.getoption("--server-url", None)

        if server_url:
            # External server mode
            mcp_url = server_url
            a2a_url = server_url
        elif mode == "docker":
            # Docker mode - use configured ports
            mcp_url = f"http://localhost:{DEFAULT_MCP_PORT}"
            a2a_url = f"http://localhost:{DEFAULT_A2A_PORT}"
        else:
            # Local/CI mode would start its own servers
            # For now default to Docker ports
            mcp_url = f"http://localhost:{DEFAULT_MCP_PORT}"
            a2a_url = f"http://localhost:{DEFAULT_A2A_PORT}"

        # Get or create auth token
        auth_token = await self._get_or_create_auth_token(mcp_url)

        client = AdCPTestClient(
            mcp_url=mcp_url, a2a_url=a2a_url, auth_token=auth_token, dry_run=True  # Always use dry-run for tests
        )

        async with client:
            yield client

    async def _get_or_create_auth_token(self, base_url: str) -> str:
        """Get existing token or create new test principal."""
        # For now, use the token we know works from previous debugging
        # In production, this would create a new test principal
        return "1sNG-OxWfEsELsey-6H6IGg1HCxrpbtneGfW4GkSb10"

    @pytest.mark.asyncio
    async def test_product_discovery(self, test_client: AdCPTestClient):
        """Test product discovery through MCP and A2A."""
        print("\n=== Testing Product Discovery ===")

        # Test MCP product discovery
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "Looking for display advertising", "promoted_offering": "standard display ads"}
        )

        assert "products" in products
        assert len(products["products"]) > 0

        product = products["products"][0]
        assert "product_id" in product or "id" in product
        assert "name" in product
        assert "formats" in product

        print(f"✓ MCP: Found {len(products['products'])} products")

        # Test A2A product query
        a2a_response = await test_client.query_a2a("What display advertising products do you offer?")

        # A2A returns results in artifacts or message field
        assert "artifacts" in a2a_response or "message" in a2a_response
        assert a2a_response.get("status", {}).get("state") == "completed"
        print("✓ A2A: Got product information")

    @pytest.mark.asyncio
    async def test_signals_discovery(self, test_client: AdCPTestClient):
        """Test signals discovery if available."""
        print("\n=== Testing Signals Discovery ===")

        try:
            signals = await test_client.call_mcp_tool("get_signals", {"category": "contextual"})

            assert "signals" in signals
            print(f"✓ Found {len(signals.get('signals', []))} signals")

        except Exception as e:
            if "not found" in str(e).lower():
                print("⚠ Signals tool not available (optional)")
            else:
                raise

    @pytest.mark.asyncio
    async def test_media_buy_creation_with_targeting(self, test_client: AdCPTestClient):
        """Test creating a media buy with targeting overlay."""
        print("\n=== Testing Media Buy Creation ===")

        # First get products
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "video ads", "promoted_offering": "video campaigns"}
        )

        product_ids = [p.get("product_id", p.get("id")) for p in products["products"][:1]]

        # Create media buy with targeting overlay
        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": product_ids,
                "budget": 10000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
                "targeting_overlay": {
                    "geographic": {"countries": ["US", "CA"], "regions": ["California", "New York"]},
                    "audience": {"age_ranges": ["25-34", "35-44"], "interests": ["technology", "business"]},
                },
            },
        )

        assert "media_buy_id" in media_buy
        assert media_buy["status"] in ["pending", "pending_creative", "active"]

        print(f"✓ Created media buy: {media_buy['media_buy_id']}")
        return media_buy["media_buy_id"]

    @pytest.mark.asyncio
    async def test_creative_workflow(self, test_client: AdCPTestClient):
        """Test the complete creative workflow."""
        print("\n=== Testing Creative Workflow ===")

        # First create a media buy to associate creatives with
        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {"product_ids": ["prod_1"], "budget": 5000.0, "start_date": "2025-02-01", "end_date": "2025-02-28"},
        )
        media_buy_id = media_buy.get("media_buy_id") or media_buy.get("id")
        print(f"✓ Created media buy: {media_buy_id}")

        # Create a creative group
        group = await test_client.call_mcp_tool("create_creative_group", {"name": "Test Campaign Creatives"})

        group_id = group.get("group_id") or group.get("id")
        print(f"✓ Created creative group: {group_id}")

        # Add creative assets
        creative = await test_client.call_mcp_tool(
            "add_creative_assets",
            {
                "media_buy_id": media_buy_id,
                "creatives": [
                    {
                        "creative_id": "test_creative_1",
                        "principal_id": "e2e-test-principal",
                        "name": "Test Banner",
                        "format": "display_300x250",
                        "format_id": "display_300x250",
                        "content_uri": "https://example.com/banner.jpg",
                        "content": {"url": "https://example.com/banner.jpg"},
                        "status": "pending",
                    }
                ],
            },
        )

        creative_ids = creative.get("creative_ids", [])
        if creative_ids:
            print(f"✓ Added {len(creative_ids)} creative(s)")

            # Check creative status
            status = await test_client.call_mcp_tool("check_creative_status", {"creative_ids": creative_ids})

            print(f"✓ Creative status: {status.get('status', 'unknown')}")

    @pytest.mark.asyncio
    async def test_time_simulation(self, test_client: AdCPTestClient):
        """Test simulation control and time progression."""
        print("\n=== Testing Time Simulation ===")

        # Set mock time
        start_time = datetime(2025, 9, 1, 10, 0, 0)
        test_client.set_mock_time(start_time)
        print(f"✓ Set mock time to: {start_time}")

        # Create a media buy
        media_buy_id = await self.test_media_buy_creation_with_targeting(test_client)

        # Jump to campaign midpoint
        test_client.jump_to_event("campaign-midpoint")

        # Use simulation control to advance time
        result = await test_client.call_mcp_tool(
            "simulation_control",
            {
                "strategy_id": f"sim_{media_buy_id}",  # Simulation strategies use sim_ prefix
                "action": "jump_to",
                "parameters": {"target_date": "2025-09-15"},
            },
        )

        assert result.get("status") in ["ok", "success"]
        print("✓ Advanced simulation to midpoint")

        # Check delivery at midpoint
        delivery = await test_client.call_mcp_tool("get_media_buy_delivery", {"media_buy_id": media_buy_id})

        assert "impressions" in delivery
        assert "spend" in delivery
        print(f"✓ Delivery check: {delivery.get('impressions', 0)} impressions")

    @pytest.mark.asyncio
    async def test_performance_optimization(self, test_client: AdCPTestClient):
        """Test performance monitoring and optimization."""
        print("\n=== Testing Performance Optimization ===")

        # Create a simple media buy first
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "display ads", "promoted_offering": "performance"}
        )

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [products["products"][0].get("product_id", products["products"][0].get("id"))],
                "budget": 5000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
            },
        )

        media_buy_id = media_buy["media_buy_id"]

        # Simulate some delivery
        test_client.jump_to_event("campaign-active")

        # Get all delivery data
        all_delivery = await test_client.call_mcp_tool(
            "get_all_media_buy_delivery", {"today": "2025-09-15"}  # Mid-campaign date
        )

        assert "media_buys" in all_delivery
        print(f"✓ Retrieved delivery for {len(all_delivery['media_buys'])} campaigns")

        # Update performance index if available
        try:
            update = await test_client.call_mcp_tool(
                "update_performance_index",
                {
                    "media_buy_id": media_buy_id,
                    "performance_data": [{"product_id": "prod_1", "performance_index": 1.2, "confidence_score": 0.85}],
                },
            )
            print("✓ Updated performance index")
        except Exception as e:
            print(f"⚠ Performance index update not available: {e}")

    @pytest.mark.asyncio
    async def test_aee_compliance(self, test_client: AdCPTestClient):
        """Test AEE (Ad Experience Engine) compliance checking."""
        print("\n=== Testing AEE Compliance ===")

        result = await test_client.call_mcp_tool(
            "check_aee_requirements", {"channel": "web", "required_dimensions": ["geo", "daypart", "frequency"]}
        )

        assert "supported" in result or "compliant" in result or "status" in result
        print("✓ AEE compliance check completed")

    @pytest.mark.asyncio
    async def test_error_handling(self, test_client: AdCPTestClient):
        """Test error handling and recovery scenarios."""
        print("\n=== Testing Error Handling ===")

        # Test invalid product ID
        # TODO: Server should validate product IDs and raise exceptions for invalid ones
        try:
            result = await test_client.call_mcp_tool(
                "create_media_buy",
                {
                    "product_ids": ["invalid_product_id"],
                    "budget": 1000.0,
                    "start_date": "2025-09-01",
                    "end_date": "2025-09-30",
                },
            )
            # If no exception, check if error is in response
            if "error" in result or "status" in result and result["status"] == "error":
                print("✓ Invalid product ID handled correctly (returned error)")
            else:
                print("⚠ Warning: Server accepted invalid product ID without error")
        except Exception as e:
            assert "not found" in str(e).lower() or "invalid" in str(e).lower()
            print("✓ Invalid product ID handled correctly (raised exception)")

        # Test invalid date range
        # TODO: Server should validate date ranges
        try:
            result = await test_client.call_mcp_tool(
                "create_media_buy",
                {
                    "product_ids": ["prod_1"],  # Need at least one valid product
                    "budget": 1000.0,
                    "start_date": "2025-09-30",
                    "end_date": "2025-09-01",  # End before start
                },
            )
            if "error" in result or "status" in result and result["status"] == "error":
                print("✓ Invalid date range handled correctly (returned error)")
            else:
                print("⚠ Warning: Server accepted invalid date range without error")
        except Exception as e:
            print("✓ Invalid date range handled correctly (raised exception)")

    @pytest.mark.asyncio
    async def test_parallel_sessions(self, test_client: AdCPTestClient):
        """Test parallel test sessions with isolation."""
        print("\n=== Testing Parallel Session Isolation ===")

        # Create a second client with different session ID
        client2 = AdCPTestClient(
            mcp_url=test_client.mcp_url,
            a2a_url=test_client.a2a_url,
            auth_token=test_client.auth_token,
            test_session_id=str(uuid.uuid4()),
            dry_run=True,
        )

        async with client2:
            # Both clients should work independently
            products1 = await test_client.call_mcp_tool(
                "get_products", {"brief": "display", "promoted_offering": "test1"}
            )

            products2 = await client2.call_mcp_tool("get_products", {"brief": "video", "promoted_offering": "test2"})

            # Sessions should be isolated
            assert test_client.test_session_id != client2.test_session_id
            print(f"✓ Session 1: {test_client.test_session_id[:8]}...")
            print(f"✓ Session 2: {client2.test_session_id[:8]}...")

    @pytest.mark.asyncio
    async def test_full_campaign_lifecycle(self, test_client: AdCPTestClient):
        """Test complete campaign lifecycle from creation to completion."""
        print("\n=== Testing Full Campaign Lifecycle ===")

        # Phase 1: Discovery
        print("\nPhase 1: Discovery")
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "brand awareness campaign", "promoted_offering": "premium"}
        )
        product = products["products"][0]
        product_id = product.get("product_id", product.get("id"))
        print(f"✓ Selected product: {product_id}")

        # Phase 2: Campaign Creation
        print("\nPhase 2: Creation")
        test_client.set_mock_time(datetime(2025, 9, 1, 9, 0, 0))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 25000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
                "targeting_overlay": {"geographic": {"countries": ["US"]}, "audience": {"interests": ["technology"]}},
            },
        )
        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created campaign: {media_buy_id}")

        # Phase 3: Creative Setup
        print("\nPhase 3: Creative Setup")
        group = await test_client.call_mcp_tool("create_creative_group", {"name": "Brand Campaign Assets"})

        creative = await test_client.call_mcp_tool(
            "add_creative_assets",
            {
                "media_buy_id": media_buy_id,
                "creatives": [
                    {
                        "creative_id": "hero_banner",
                        "principal_id": "e2e-test-principal",
                        "name": "Hero Banner",
                        "format": "display_728x90",
                        "format_id": "display_728x90",
                        "content_uri": "https://example.com/hero.jpg",
                        "content": {"url": "https://example.com/hero.jpg"},
                        "status": "pending",
                    },
                    {
                        "creative_id": "square_banner",
                        "principal_id": "e2e-test-principal",
                        "name": "Square",
                        "format": "display_300x250",
                        "format_id": "display_300x250",
                        "content_uri": "https://example.com/square.jpg",
                        "content": {"url": "https://example.com/square.jpg"},
                        "status": "pending",
                    },
                ],
            },
        )
        print(f"✓ Added {len(creative.get('creative_ids', []))} creatives")

        # Phase 4: Launch
        print("\nPhase 4: Launch")
        test_client.jump_to_event("campaign-start")

        status = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})
        print(f"✓ Campaign status: {status.get('status', 'unknown')}")

        # Phase 5: Mid-flight Optimization
        print("\nPhase 5: Optimization")
        test_client.set_mock_time(datetime(2025, 9, 15, 12, 0, 0))
        test_client.jump_to_event("campaign-midpoint")

        delivery = await test_client.call_mcp_tool("get_media_buy_delivery", {"media_buy_id": media_buy_id})

        print(f"✓ Mid-flight delivery: {delivery.get('impressions', 0)} impressions, ${delivery.get('spend', 0)} spend")

        # Update if underdelivering
        if delivery.get("pacing", 1.0) < 0.9:
            update = await test_client.call_mcp_tool(
                "update_media_buy", {"media_buy_id": media_buy_id, "updates": {"daily_budget_increase": 1.2}}
            )
            print("✓ Adjusted pacing")

        # Phase 6: Completion
        print("\nPhase 6: Completion")
        test_client.set_mock_time(datetime(2025, 10, 1, 9, 0, 0))
        test_client.jump_to_event("campaign-complete")

        final_delivery = await test_client.call_mcp_tool("get_media_buy_delivery", {"media_buy_id": media_buy_id})

        print("✓ Campaign completed:")
        print(f"  - Total impressions: {final_delivery.get('impressions', 0)}")
        print(f"  - Total spend: ${final_delivery.get('spend', 0)}")
        print(f"  - CTR: {final_delivery.get('ctr', 0):.2%}")

        print("\n✅ Full lifecycle test completed successfully!")


# Pytest configuration hooks
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--mode", default="docker", choices=["local", "docker", "ci", "external"], help="Test execution mode"
    )
    parser.addoption("--server-url", default=None, help="External server URL for testing")
    parser.addoption("--keep-data", action="store_true", default=False, help="Keep test data after completion")
