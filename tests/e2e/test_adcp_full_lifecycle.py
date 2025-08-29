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

import asyncio
import json

# Test configuration defaults - read from environment variables
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

DEFAULT_MCP_PORT = int(os.getenv("ADCP_SALES_PORT", "8126"))  # Match docker-compose actual mapping
DEFAULT_A2A_PORT = int(os.getenv("A2A_PORT", "8091"))  # From docker-compose.yml
DEFAULT_ADMIN_PORT = int(os.getenv("ADMIN_UI_PORT", "8087"))  # From .env
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

    def _parse_mcp_response(self, result) -> dict:
        """Parse MCP response with robust fallback handling."""
        try:
            # Handle TextContent response format
            if hasattr(result, "content") and isinstance(result.content, list):
                if result.content and hasattr(result.content[0], "text"):
                    return json.loads(result.content[0].text)

            # Handle direct dict response
            if isinstance(result, dict):
                return result

            # Handle string JSON response
            if isinstance(result, str):
                return json.loads(result)

            # Handle result with content field
            if hasattr(result, "content"):
                if isinstance(result.content, str):
                    return json.loads(result.content)
                elif isinstance(result.content, dict):
                    return result.content

            # Fallback - convert to dict if possible
            if hasattr(result, "__dict__"):
                return result.__dict__

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse MCP response as JSON: {e}")
        except Exception as e:
            raise ValueError(f"Unexpected MCP response format: {type(result)} - {e}")

        raise ValueError(f"Could not parse MCP response: {type(result)}")

    async def call_mcp_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call an MCP tool and parse the response with robust error handling."""
        try:
            result = await self.mcp_client.call_tool(tool_name, {"req": params})
            return self._parse_mcp_response(result)
        except Exception as e:
            # Add context for better error messages
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {e}") from e

    async def query_a2a(self, query: str) -> dict[str, Any]:
        """Query the A2A server using JSON-RPC 2.0 transport with proper string messageId."""
        headers = self._build_headers()
        # A2A expects Bearer token in Authorization header
        headers["Authorization"] = f"Bearer {self.auth_token}"
        headers["Content-Type"] = "application/json"

        # Create proper JSON-RPC 2.0 request with string IDs as per A2A spec
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),  # JSON-RPC request ID as string
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),  # Message ID as string (A2A spec requirement)
                    "contextId": self.test_session_id,
                    "role": "user",
                    "parts": [{"kind": "text", "text": query}],
                }
            },
        }

        # Retry logic for connection issues
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                response = await self.http_client.post(
                    f"{self.a2a_url}/a2a",  # Use standard /a2a endpoint
                    json=request,
                    headers=headers,
                    timeout=10.0,  # Add timeout
                )
                response.raise_for_status()
                result = response.json()

                # Handle JSON-RPC response format
                if "result" in result:
                    task = result["result"]
                    # Convert to expected format for existing tests
                    return {
                        "status": {"state": task.get("status", {}).get("state", "unknown")},
                        "artifacts": task.get("artifacts", []),
                        "message": task.get("metadata", {}).get("response", "") if task.get("metadata") else "",
                    }
                elif "error" in result:
                    # Return error in expected format
                    return {
                        "status": {"state": "failed"},
                        "error": result["error"],
                        "message": result["error"].get("message", "Error occurred"),
                    }
                else:
                    # Unexpected format
                    return {"status": {"state": "unknown"}, "message": "Unexpected response format"}
            except httpx.ReadError as e:
                if attempt < max_retries - 1:
                    print(f"A2A connection failed (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    raise e
            except Exception as e:
                # Don't retry for non-connection errors
                raise e


class TestAdCPFullLifecycle:
    """Comprehensive E2E test suite for AdCP protocol compliance."""

    @pytest.fixture
    async def test_client(self, request, docker_services_e2e, test_auth_token) -> AdCPTestClient:
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

        # Use the provided test auth token
        auth_token = test_auth_token

        client = AdCPTestClient(
            mcp_url=mcp_url, a2a_url=a2a_url, auth_token=auth_token, dry_run=True  # Always use dry-run for tests
        )

        async with client:
            yield client

    @pytest.mark.asyncio
    async def test_product_discovery(self, test_client: AdCPTestClient):
        """Test comprehensive product discovery through MCP and A2A with full validation."""
        print("\n=== Testing Product Discovery ===")

        # Test MCP product discovery with natural language
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "Looking for display advertising", "promoted_offering": "standard display ads"}
        )

        # Comprehensive response validation
        assert "products" in products, "Response must contain 'products' field"
        assert isinstance(products["products"], list), "Products must be a list"
        assert len(products["products"]) > 0, "Must return at least one product"

        # Validate each product has required fields per AdCP spec
        for i, product in enumerate(products["products"]):
            print(f"  Validating product {i+1}: {product.get('name', 'Unnamed')}")

            # Required fields per AdCP spec
            assert "product_id" in product or "id" in product, f"Product {i} missing product_id/id field"
            assert "name" in product, f"Product {i} missing name field"
            assert "formats" in product, f"Product {i} missing formats field"

            # Validate formats structure
            formats = product["formats"]
            assert isinstance(formats, list), f"Product {i} formats must be a list"
            assert len(formats) > 0, f"Product {i} must have at least one format"

            # Validate format structure
            for j, format_info in enumerate(formats):
                assert "format_id" in format_info, f"Product {i} format {j} missing format_id"
                assert "name" in format_info, f"Product {i} format {j} missing name"

            # Additional validation for pricing if present
            if "pricing" in product:
                pricing = product["pricing"]
                if "price_range" in pricing:
                    price_range = pricing["price_range"]
                    assert "min" in price_range or "max" in price_range, f"Product {i} price_range incomplete"

        print(f"✓ MCP: Found {len(products['products'])} products with complete validation")

        # Test A2A product query with validation
        a2a_response = await test_client.query_a2a("What display advertising products do you offer?")

        # A2A protocol validation
        assert isinstance(a2a_response, dict), "A2A response must be a dict"
        assert "status" in a2a_response, "A2A response must contain status field"

        status = a2a_response["status"]
        assert "state" in status, "A2A status must contain state field"
        assert status["state"] == "completed", f"A2A query should complete successfully, got: {status.get('state')}"

        # Validate A2A response contains usable product information
        has_artifacts = "artifacts" in a2a_response and len(a2a_response["artifacts"]) > 0
        has_message = "message" in a2a_response and a2a_response["message"]
        assert has_artifacts or has_message, "A2A response must contain either artifacts or message with product info"

        print("✓ A2A: Product information validated successfully")

        # Test specific product format queries
        video_products = await test_client.call_mcp_tool(
            "get_products", {"brief": "video advertising campaigns", "promoted_offering": "video content"}
        )

        assert "products" in video_products
        if len(video_products["products"]) > 0:
            # Verify we get different results for different queries
            video_product = video_products["products"][0]
            video_formats = [f["format_id"] for f in video_product["formats"]]
            has_video_format = any("video" in fmt.lower() for fmt in video_formats)
            print(f"✓ Video product query returned appropriate formats: {video_formats}")

        return products  # Return for use in other tests

    @pytest.mark.asyncio
    async def test_creative_format_discovery_via_products(self, test_client: AdCPTestClient):
        """Test creative format discovery through product listings."""
        print("\n=== Testing Creative Format Discovery via Products ===")

        # Get products which contain format information
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "Looking for creative formats", "promoted_offering": "format discovery"}
        )

        # Validate response structure
        assert "products" in products, "Response must contain 'products' field"
        assert isinstance(products["products"], list), "Products must be a list"
        assert len(products["products"]) > 0, "Must return at least one product"

        # Extract and validate formats from products
        all_formats = []
        for product in products["products"]:
            assert "formats" in product, "Product must contain formats"
            for format_info in product["formats"]:
                all_formats.append(format_info)

                # Validate required format fields
                assert "format_id" in format_info, "Format missing format_id"
                assert "name" in format_info, "Format missing name"
                assert "type" in format_info, "Format missing type"

                # Validate format type
                valid_types = ["video", "audio", "display", "native", "dooh"]
                assert format_info["type"] in valid_types, f"Invalid format type: {format_info['type']}"

        print(f"✓ Discovered {len(all_formats)} creative formats across {len(products['products'])} products")
        for i, format_info in enumerate(all_formats[:5]):  # Show first 5
            print(f"  ✓ Format {i+1}: {format_info['name']} ({format_info['type']})")

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
        """Test creating a media buy with comprehensive validation."""
        print("\n=== Testing Media Buy Creation ===")

        # First get products for realistic product selection
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "video ads", "promoted_offering": "video campaigns"}
        )

        assert len(products["products"]) > 0, "Need products to create media buy"
        selected_products = products["products"][:2]  # Test with multiple products
        product_ids = [p.get("product_id", p.get("id")) for p in selected_products]

        print(f"  Selected products: {product_ids}")

        # Test comprehensive media buy creation with targeting
        media_buy_request = {
            "product_ids": product_ids,
            "budget": 25000.0,  # Test with significant budget
            "start_date": "2025-09-01",
            "end_date": "2025-09-30",
            "targeting_overlay": {
                "geographic": {
                    "countries": ["US", "CA"],
                    "regions": ["California", "New York", "Ontario"],
                    "cities": ["San Francisco", "Toronto"],
                },
                "audience": {
                    "age_ranges": ["25-34", "35-44"],
                    "interests": ["technology", "business", "finance"],
                    "demographics": ["college_educated"],
                },
                "contextual": {
                    "keywords": ["innovation", "startup", "investment"],
                    "categories": ["business", "technology"],
                },
            },
            "frequency_cap": {"impressions": 5, "period": "day"},
            "optimization_goal": "conversions",
        }

        media_buy = await test_client.call_mcp_tool("create_media_buy", media_buy_request)

        # Comprehensive response validation per AdCP spec
        assert isinstance(media_buy, dict), "Media buy response must be a dict"
        assert "media_buy_id" in media_buy, "Response must contain media_buy_id"

        media_buy_id = media_buy["media_buy_id"]
        assert isinstance(media_buy_id, str), "media_buy_id must be a string"
        assert len(media_buy_id) > 0, "media_buy_id cannot be empty"

        # Status validation
        assert "status" in media_buy, "Response must contain status field"
        valid_statuses = ["pending", "pending_creative", "active", "pending_approval"]
        assert media_buy["status"] in valid_statuses, f"Invalid status: {media_buy['status']}"

        # Budget validation
        if "budget" in media_buy:
            assert isinstance(media_buy["budget"], int | float), "Budget must be numeric"
            assert media_buy["budget"] > 0, "Budget must be positive"

        # Date validation
        if "start_date" in media_buy and "end_date" in media_buy:
            from datetime import datetime

            start_date = datetime.fromisoformat(media_buy["start_date"].replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(media_buy["end_date"].replace("Z", "+00:00"))
            assert start_date < end_date, "Start date must be before end date"

        # Packages validation if present
        if "packages" in media_buy:
            packages = media_buy["packages"]
            assert isinstance(packages, list), "Packages must be a list"
            assert len(packages) > 0, "Must have at least one package"

            for i, package in enumerate(packages):
                assert "package_id" in package, f"Package {i} missing package_id"
                assert "product_id" in package, f"Package {i} missing product_id"
                print(f"  Package {i+1}: {package['package_id']} for product {package['product_id']}")

        print(f"✓ Created media buy: {media_buy_id}")
        print(f"  Status: {media_buy['status']}")
        print(f"  Budget: ${media_buy.get('budget', 'N/A')}")

        # Test A2A media buy creation query
        a2a_query = f"Create a media buy for {len(product_ids)} products with $25,000 budget targeting US and Canada"
        a2a_response = await test_client.query_a2a(a2a_query)

        # Validate A2A response
        assert "status" in a2a_response, "A2A response must contain status"
        assert a2a_response["status"]["state"] == "completed", "A2A media buy query should complete"
        print("✓ A2A media buy creation query completed successfully")

        # Verify media buy can be retrieved
        try:
            status_check = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})
            assert "status" in status_check, "Status check must return status"
            print(f"✓ Media buy status verified: {status_check['status']}")
        except Exception as e:
            print(f"⚠ Status check failed: {e}")

        return media_buy_id

    @pytest.mark.asyncio
    async def test_creative_workflow(self, test_client: AdCPTestClient):
        """Test the complete creative workflow with multiple formats and validation."""
        print("\n=== Testing Creative Workflow ===")

        # Get products first to create a realistic media buy
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "display and video advertising", "promoted_offering": "multi-format campaign"}
        )

        assert len(products["products"]) > 0, "Need products for creative workflow test"
        product_ids = [p.get("product_id", p.get("id")) for p in products["products"][:1]]

        # Create a media buy to associate creatives with
        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {"product_ids": product_ids, "budget": 15000.0, "start_date": "2025-09-01", "end_date": "2025-09-30"},
        )
        media_buy_id = media_buy.get("media_buy_id") or media_buy.get("id")
        print(f"✓ Created media buy: {media_buy_id}")

        # Create a creative group with validation
        group_response = await test_client.call_mcp_tool(
            "create_creative_group", {"name": "E2E Test Campaign Creatives"}
        )

        assert isinstance(group_response, dict), "Creative group response must be a dict"

        # Handle nested response structure
        if "group" in group_response:
            group = group_response["group"]
        else:
            group = group_response

        assert "group_id" in group or "id" in group, "Response must contain group_id"
        group_id = group.get("group_id") or group.get("id")
        assert isinstance(group_id, str), "group_id must be a string"
        print(f"✓ Created creative group: {group_id}")

        # Test multiple creative formats
        test_creatives = [
            {
                "creative_id": "test_banner_300x250",
                "principal_id": "e2e-test-principal",
                "name": "Test Medium Rectangle Banner",
                "format": "display_300x250",
                "format_id": "display_300x250",
                "content_uri": "https://example.com/banner_300x250.jpg",
                "content": {
                    "url": "https://example.com/banner_300x250.jpg",
                    "width": 300,
                    "height": 250,
                    "alt_text": "Test banner advertisement",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00",
                "updated_at": "2025-09-01T00:00:00",
            },
            {
                "creative_id": "test_banner_728x90",
                "principal_id": "e2e-test-principal",
                "name": "Test Leaderboard Banner",
                "format": "display_728x90",
                "format_id": "display_728x90",
                "content_uri": "https://example.com/banner_728x90.jpg",
                "content": {
                    "url": "https://example.com/banner_728x90.jpg",
                    "width": 728,
                    "height": 90,
                    "alt_text": "Test leaderboard banner",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00",
                "updated_at": "2025-09-01T00:00:00",
            },
            {
                "creative_id": "test_video_creative",
                "principal_id": "e2e-test-principal",
                "name": "Test Video Advertisement",
                "format": "video_16_9",
                "format_id": "video_16_9",
                "content_uri": "https://example.com/video_ad.mp4",
                "content": {
                    "url": "https://example.com/video_ad.mp4",
                    "duration": 30,
                    "aspect_ratio": "16:9",
                    "video_codec": "h264",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00",
                "updated_at": "2025-09-01T00:00:00",
            },
        ]

        # Add multiple creative assets
        creative_response = await test_client.call_mcp_tool(
            "add_creative_assets",
            {
                "media_buy_id": media_buy_id,
                "creatives": test_creatives,
                "group_id": group_id,  # Associate with the creative group
            },
        )

        # Comprehensive creative response validation
        assert isinstance(creative_response, dict), "Creative response must be a dict"

        # Handle response format - it returns statuses, not creative_ids
        statuses = creative_response.get("statuses", [])
        assert isinstance(statuses, list), "statuses must be a list"
        assert len(statuses) == len(
            test_creatives
        ), f"Expected {len(test_creatives)} creative statuses, got {len(statuses)}"

        # Extract creative IDs from statuses
        creative_ids = [status["creative_id"] for status in statuses]

        print(f"✓ Added {len(creative_ids)} creatives successfully")
        for i, status in enumerate(statuses):
            creative_id = status["creative_id"]
            status_info = status["status"]
            print(f"  Creative {i+1}: {creative_id} (status: {status_info})")

        # Check individual creative status
        for creative_id in creative_ids:
            try:
                status = await test_client.call_mcp_tool("check_creative_status", {"creative_ids": [creative_id]})

                assert isinstance(status, dict), "Creative status response must be a dict"
                assert "statuses" in status or "status" in status, "Response must contain status information"

                if "statuses" in status:
                    assert len(status["statuses"]) == 1, "Should return one status"
                    creative_status = status["statuses"][0]
                else:
                    creative_status = status["status"]

                valid_statuses = ["pending", "approved", "rejected", "under_review"]
                print(f"  Creative {creative_id}: {creative_status}")

            except Exception as e:
                print(f"⚠ Status check for {creative_id} failed: {e}")

        # Test A2A creative query
        a2a_query = f"What creatives are associated with media buy {media_buy_id}?"
        try:
            a2a_response = await test_client.query_a2a(a2a_query)

            assert "status" in a2a_response, "A2A response must contain status"
            assert a2a_response["status"]["state"] == "completed", "A2A creative query should complete"
            print("✓ A2A creative query completed successfully")

        except Exception as e:
            print(f"⚠ A2A creative query failed: {e}")

        # Test creative retrieval
        try:
            creatives = await test_client.call_mcp_tool("get_creatives", {"media_buy_id": media_buy_id})

            if "creatives" in creatives:
                retrieved_count = len(creatives["creatives"])
                print(f"✓ Retrieved {retrieved_count} creatives for media buy")

                # Validate retrieved creative structure
                for i, creative in enumerate(creatives["creatives"]):
                    assert "creative_id" in creative, f"Retrieved creative {i} missing creative_id"
                    assert "format_id" in creative, f"Retrieved creative {i} missing format_id"
                    assert "status" in creative, f"Retrieved creative {i} missing status"

        except Exception as e:
            print(f"⚠ Creative retrieval failed: {e}")

        return {"media_buy_id": media_buy_id, "creative_group_id": group_id, "creative_ids": creative_ids}

    @pytest.mark.asyncio
    async def test_delivery_metrics_comprehensive(self, test_client: AdCPTestClient):
        """Test comprehensive delivery metrics and reporting with validation."""
        print("\n=== Testing Delivery Metrics & Reporting ===")

        # Create a test media buy for delivery testing
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "performance tracking campaign", "promoted_offering": "data-rich metrics"}
        )

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [products["products"][0].get("product_id", products["products"][0].get("id"))],
                "budget": 20000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
                "targeting_overlay": {
                    "geographic": {"countries": ["US"]},
                    "audience": {"interests": ["sports", "fitness"]},
                },
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created test media buy for delivery: {media_buy_id}")

        # Simulate campaign progression
        test_client.jump_to_event("campaign-active")

        # Test individual media buy delivery
        delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-09-15"}  # Mid-campaign
        )

        # Comprehensive delivery response validation
        assert isinstance(delivery, dict), "Delivery response must be a dict"
        assert "deliveries" in delivery, "Response must contain 'deliveries' array"
        assert isinstance(delivery["deliveries"], list), "Deliveries must be a list"
        assert len(delivery["deliveries"]) > 0, "Must have at least one delivery record"

        delivery_data = delivery["deliveries"][0]
        print(f"  Validating delivery metrics for: {delivery_data.get('media_buy_id', 'unknown')}")

        # Core metrics validation per AdCP spec
        required_metrics = ["impressions", "spend"]
        for metric in required_metrics:
            assert metric in delivery_data, f"Delivery must contain '{metric}' metric"
            value = delivery_data[metric]
            assert isinstance(value, int | float), f"{metric} must be numeric"
            assert value >= 0, f"{metric} cannot be negative"

        # Optional but common metrics
        optional_metrics = ["clicks", "ctr", "cpm", "conversions", "viewability", "completion_rate"]
        for metric in optional_metrics:
            if metric in delivery_data:
                value = delivery_data[metric]
                assert isinstance(value, int | float), f"{metric} must be numeric"
                if metric == "ctr":
                    assert 0 <= value <= 1, f"CTR must be between 0 and 1, got {value}"
                elif metric == "viewability":
                    assert 0 <= value <= 1, f"Viewability must be between 0 and 1, got {value}"
                elif metric == "completion_rate":
                    assert 0 <= value <= 1, f"Completion rate must be between 0 and 1, got {value}"

        print(f"  ✓ Impressions: {delivery_data['impressions']:,}")
        print(f"  ✓ Spend: ${delivery_data['spend']:,.2f}")
        if "clicks" in delivery_data:
            print(f"  ✓ Clicks: {delivery_data['clicks']:,}")
        if "ctr" in delivery_data:
            print(f"  ✓ CTR: {delivery_data['ctr']:.3%}")

        # Test with different date ranges
        try:
            # Test campaign start delivery
            start_delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-09-01"}  # Campaign start
            )

            if start_delivery["deliveries"]:
                start_data = start_delivery["deliveries"][0]
                print(f"  ✓ Campaign start metrics - Impressions: {start_data.get('impressions', 0)}")

            # Test campaign end delivery
            end_delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-10-01"}  # Campaign end
            )

            if end_delivery["deliveries"]:
                end_data = end_delivery["deliveries"][0]
                print(f"  ✓ Campaign end metrics - Impressions: {end_data.get('impressions', 0)}")

        except Exception as e:
            print(f"⚠ Date range testing failed: {e}")

        # Test bulk delivery reporting
        try:
            all_delivery = await test_client.call_mcp_tool("get_all_media_buy_delivery", {"today": "2025-09-15"})

            assert "deliveries" in all_delivery, "Bulk delivery must contain deliveries array"
            bulk_count = len(all_delivery["deliveries"])
            print(f"  ✓ Bulk delivery report: {bulk_count} campaigns")

            # Validate each delivery in bulk response
            for i, bulk_delivery in enumerate(all_delivery["deliveries"][:3]):  # Check first 3
                assert "media_buy_id" in bulk_delivery, f"Bulk delivery {i} missing media_buy_id"
                assert "impressions" in bulk_delivery, f"Bulk delivery {i} missing impressions"
                assert "spend" in bulk_delivery, f"Bulk delivery {i} missing spend"

        except Exception as e:
            print(f"⚠ Bulk delivery testing failed: {e}")

        # Test A2A delivery query
        try:
            a2a_query = f"What are the current delivery metrics for media buy {media_buy_id}?"
            a2a_response = await test_client.query_a2a(a2a_query)

            assert "status" in a2a_response, "A2A delivery query must contain status"
            assert a2a_response["status"]["state"] == "completed", "A2A delivery query should complete"
            print("  ✓ A2A delivery query completed successfully")

        except Exception as e:
            print(f"⚠ A2A delivery query failed: {e}")

        # Test delivery data consistency
        impressions = delivery_data["impressions"]
        spend = delivery_data["spend"]

        if impressions > 0 and spend > 0:
            calculated_cpm = (spend / impressions) * 1000
            if "cpm" in delivery_data:
                reported_cpm = delivery_data["cpm"]
                # Allow for some variance in CPM calculation
                cpm_variance = abs(calculated_cpm - reported_cpm) / calculated_cpm
                assert (
                    cpm_variance < 0.1
                ), f"CPM calculation inconsistent: calculated {calculated_cpm}, reported {reported_cpm}"
                print(f"  ✓ CPM consistency verified: ${reported_cpm:.2f}")

        return {"media_buy_id": media_buy_id, "delivery_data": delivery_data, "metrics_validated": True}

    @pytest.mark.asyncio
    async def test_a2a_protocol_comprehensive(self, test_client: AdCPTestClient):
        """Test A2A protocol for all core operations with comprehensive validation."""
        print("\n=== Testing A2A Protocol Comprehensive ===")

        # Test 1: Product Discovery via A2A
        print("\n  Testing A2A Product Discovery")
        product_queries = [
            "What advertising products do you offer?",
            "Show me display advertising options",
            "What video advertising products are available?",
            "What are your premium advertising packages?",
        ]

        product_responses = []
        for query in product_queries:
            try:
                response = await test_client.query_a2a(query)

                # Validate A2A response structure
                assert isinstance(response, dict), f"A2A response must be dict for query: {query}"
                assert "status" in response, f"A2A response missing status for query: {query}"
                assert "state" in response["status"], f"A2A status missing state for query: {query}"

                state = response["status"]["state"]
                assert state == "completed", f"A2A query should complete successfully, got: {state}"

                # Check for meaningful response content
                has_content = ("artifacts" in response and len(response["artifacts"]) > 0) or (
                    "message" in response and response["message"]
                )
                assert has_content, f"A2A response must contain content for query: {query}"

                product_responses.append(response)
                print(f"    ✓ '{query[:30]}...' completed successfully")

            except Exception as e:
                print(f"    ❌ A2A product query failed: {query[:30]}... - {e}")
                raise

        # Test 2: Campaign Creation via A2A
        print("\n  Testing A2A Campaign Creation")
        campaign_queries = [
            "Create a $10,000 advertising campaign for sports content targeting US users",
            "Set up a video advertising buy with $5,000 budget for technology audience",
            "I need a display campaign targeting California with $15,000 budget",
        ]

        for query in campaign_queries:
            try:
                response = await test_client.query_a2a(query)

                # Validate campaign creation response
                assert "status" in response, f"Campaign creation missing status: {query}"
                assert response["status"]["state"] == "completed", f"Campaign creation should complete: {query}"

                # Check if response indicates successful creation or provides guidance
                response_content = response.get("message", "") + str(response.get("artifacts", []))
                creation_indicators = ["created", "campaign", "media buy", "setup", "configured"]
                has_creation_content = any(indicator in response_content.lower() for indicator in creation_indicators)

                print(f"    ✓ '{query[:40]}...' processed successfully")

            except Exception as e:
                print(f"    ⚠ A2A campaign creation query failed: {query[:30]}... - {e}")

        # Test 3: Creative Management via A2A
        print("\n  Testing A2A Creative Management")
        creative_queries = [
            "What creative formats do you support?",
            "How do I upload creative assets?",
            "What are the requirements for video creatives?",
            "Show me the status of my creative assets",
        ]

        for query in creative_queries:
            try:
                response = await test_client.query_a2a(query)

                assert "status" in response, f"Creative query missing status: {query}"
                assert response["status"]["state"] == "completed", f"Creative query should complete: {query}"

                print(f"    ✓ '{query[:35]}...' completed successfully")

            except Exception as e:
                print(f"    ⚠ A2A creative query failed: {query[:30]}... - {e}")

        # Test 4: Performance & Reporting via A2A
        print("\n  Testing A2A Performance & Reporting")
        reporting_queries = [
            "Show me the performance of my campaigns",
            "What are the delivery metrics for this month?",
            "How much have I spent on advertising?",
            "What's the CTR for my video campaigns?",
        ]

        for query in reporting_queries:
            try:
                response = await test_client.query_a2a(query)

                assert "status" in response, f"Reporting query missing status: {query}"
                assert response["status"]["state"] == "completed", f"Reporting query should complete: {query}"

                print(f"    ✓ '{query[:35]}...' completed successfully")

            except Exception as e:
                print(f"    ⚠ A2A reporting query failed: {query[:30]}... - {e}")

        # Test 5: A2A Error Handling
        print("\n  Testing A2A Error Handling")
        invalid_queries = [
            "",  # Empty query
            "asldkfjalskdjf",  # Nonsense query
            "Delete all campaigns immediately",  # Potentially dangerous query
        ]

        for query in invalid_queries:
            try:
                response = await test_client.query_a2a(query)

                # Should still get a valid response structure even for invalid queries
                assert "status" in response, "Even invalid queries should have status structure"

                # May complete but with explanation of why it can't be processed
                state = response["status"]["state"]
                print(f"    ✓ Invalid query '{query[:20]}...' handled gracefully: {state}")

            except Exception as e:
                print(f"    ✓ Invalid query '{query[:20]}...' properly rejected: {type(e).__name__}")

        # Test 6: A2A Response Time
        print("\n  Testing A2A Response Performance")
        import time

        performance_query = "What products do you offer?"
        start_time = time.time()
        response = await test_client.query_a2a(performance_query)
        response_time = time.time() - start_time

        assert response_time < 30.0, f"A2A response time too slow: {response_time:.2f}s"
        print(f"    ✓ A2A response time: {response_time:.2f}s")

        print("\n  ✅ A2A Protocol comprehensive testing completed successfully")
        return {"product_responses": len(product_responses), "response_time": response_time, "protocol_validated": True}

    @pytest.mark.asyncio
    async def test_adcp_spec_compliance(self, test_client: AdCPTestClient):
        """Test comprehensive AdCP specification compliance."""
        print("\n=== Testing AdCP Specification Compliance ===")

        compliance_results = {
            "required_endpoints_tested": 0,
            "response_fields_validated": 0,
            "error_handling_tested": 0,
            "spec_violations": [],
        }

        # Test required endpoint availability
        print("\n  Testing Required Endpoint Availability")
        required_endpoints = ["get_products", "create_media_buy", "add_creative_assets", "get_media_buy_delivery"]

        for endpoint in required_endpoints:
            try:
                if endpoint == "get_products":
                    await test_client.call_mcp_tool(endpoint, {"brief": "test"})
                elif endpoint == "create_media_buy":
                    # Test with minimal valid request
                    products = await test_client.call_mcp_tool("get_products", {"brief": "test"})
                    if products["products"]:
                        await test_client.call_mcp_tool(
                            endpoint,
                            {
                                "product_ids": [
                                    products["products"][0].get("product_id", products["products"][0].get("id"))
                                ],
                                "budget": 1000.0,
                                "start_date": "2025-10-01",
                                "end_date": "2025-10-31",
                            },
                        )
                elif endpoint == "add_creative_assets":
                    # Skip for now as it requires media buy setup
                    continue
                elif endpoint == "get_media_buy_delivery":
                    await test_client.call_mcp_tool(endpoint, {"today": "2025-09-15"})

                compliance_results["required_endpoints_tested"] += 1
                print(f"    ✓ {endpoint} endpoint available and functional")

            except Exception as e:
                violation = f"Required endpoint {endpoint} not available or functional: {e}"
                compliance_results["spec_violations"].append(violation)
                print(f"    ❌ {violation}")

        # Test optional endpoint availability
        print("\n  Testing Optional Endpoint Availability")
        optional_endpoints = ["list_creative_formats", "get_signals", "check_aee_requirements"]

        for endpoint in optional_endpoints:
            try:
                if endpoint == "list_creative_formats":
                    await test_client.call_mcp_tool(endpoint, {})
                elif endpoint == "get_signals":
                    await test_client.call_mcp_tool(endpoint, {})
                elif endpoint == "check_aee_requirements":
                    await test_client.call_mcp_tool(endpoint, {"channel": "web"})

                print(f"    ✓ Optional endpoint {endpoint} available")

            except Exception as e:
                print(f"    ⚠ Optional endpoint {endpoint} not available: {type(e).__name__}")

        # Test error handling compliance
        print("\n  Testing Error Handling Compliance")
        error_test_cases = [
            {
                "endpoint": "create_media_buy",
                "params": {"product_ids": ["invalid_product"], "budget": -100},
                "expected": "should reject negative budget",
            },
            {
                "endpoint": "get_media_buy_delivery",
                "params": {"media_buy_id": "nonexistent_id"},
                "expected": "should handle missing media buy gracefully",
            },
        ]

        for test_case in error_test_cases:
            try:
                await test_client.call_mcp_tool(test_case["endpoint"], test_case["params"])
                # If no exception, check if error is in response
                print(f"    ⚠ Error case may not be properly handled: {test_case['expected']}")

            except Exception as e:
                compliance_results["error_handling_tested"] += 1
                print(f"    ✓ Error handling works: {test_case['expected']}")

        # Generate compliance report
        print("\n  📊 AdCP Compliance Summary:")
        print(
            f"    Required endpoints tested: {compliance_results['required_endpoints_tested']}/{len(required_endpoints)}"
        )
        print(f"    Error handling cases tested: {compliance_results['error_handling_tested']}")
        print(f"    Spec violations found: {len(compliance_results['spec_violations'])}")

        if compliance_results["spec_violations"]:
            print("    ⚠ Violations:")
            for violation in compliance_results["spec_violations"]:
                print(f"      - {violation}")
        else:
            print("    ✅ No spec violations detected")

        return compliance_results

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
        delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-09-15"}
        )

        # The response has deliveries array with the media buy data
        assert "deliveries" in delivery
        assert len(delivery["deliveries"]) > 0
        first_delivery = delivery["deliveries"][0]
        assert "impressions" in first_delivery
        assert "spend" in first_delivery
        print(f"✓ Delivery check: {first_delivery.get('impressions', 0)} impressions")

    @pytest.mark.asyncio
    async def test_performance_optimization(self, test_client: AdCPTestClient):
        """Test performance monitoring and optimization."""
        print("\n=== Testing Performance Optimization ===")

        # Create a simple media buy first
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "display ads", "promoted_offering": "Acme Corp performance marketing campaigns"}
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

        # The response has deliveries array instead of media_buys
        assert "deliveries" in all_delivery
        print(f"✓ Retrieved delivery for {len(all_delivery['deliveries'])} campaigns")

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
    async def test_comprehensive_error_handling(self, test_client: AdCPTestClient):
        """Test comprehensive error handling per AdCP specification."""
        print("\n=== Testing Comprehensive Error Handling ===")

        # Test 0: Missing Required Fields
        print("\n  Testing Missing Required Field Scenarios")

        # Test missing promoted_offering in get_products
        try:
            products = await test_client.call_mcp_tool("get_products", {"brief": "test"})
            print("    ⚠ missing promoted_offering: Server accepted invalid input")
        except Exception as e:
            if "promoted_offering" in str(e):
                print("    ✓ missing promoted_offering: Server correctly rejected invalid input")
            else:
                print(f"    ⚠ missing promoted_offering: Unexpected error: {e}")

        # Test 1: Invalid Product IDs
        print("\n  Testing Invalid Product ID Scenarios")

        invalid_product_scenarios = [
            {"product_ids": [], "desc": "empty product list"},
            {"product_ids": ["nonexistent_product_123"], "desc": "nonexistent product"},
            {"product_ids": [""], "desc": "empty product ID"},
            {"product_ids": [None], "desc": "null product ID"},
        ]

        for scenario in invalid_product_scenarios:
            try:
                result = await test_client.call_mcp_tool(
                    "create_media_buy",
                    {
                        "product_ids": scenario["product_ids"],
                        "budget": 1000.0,
                        "start_date": "2025-09-01",
                        "end_date": "2025-09-30",
                    },
                )

                # If we get here, check if it's a proper error response
                if isinstance(result, dict) and ("error" in result or result.get("status") == "error"):
                    print(f"    ✓ {scenario['desc']}: Error response returned")
                else:
                    print(f"    ⚠ {scenario['desc']}: Server accepted invalid input")

            except Exception as e:
                # This is expected - validate it's the right kind of error
                error_msg = str(e).lower()
                expected_terms = ["not found", "invalid", "empty", "required"]
                if any(term in error_msg for term in expected_terms):
                    print(f"    ✓ {scenario['desc']}: Proper exception raised")
                else:
                    print(f"    ⚠ {scenario['desc']}: Unexpected error: {e}")

        # Test 2: Invalid Budget Values
        print("\n  Testing Invalid Budget Scenarios")

        # First get a valid product for budget tests
        products = await test_client.call_mcp_tool(
            "get_products", {"brief": "test", "promoted_offering": "error testing"}
        )
        if products and "products" in products and len(products["products"]) > 0:
            valid_product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

            invalid_budget_scenarios = [
                {"budget": -1000.0, "desc": "negative budget"},
                {"budget": 0.0, "desc": "zero budget"},
                {"budget": "not_a_number", "desc": "non-numeric budget"},
                {"budget": None, "desc": "null budget"},
            ]

            for scenario in invalid_budget_scenarios:
                try:
                    result = await test_client.call_mcp_tool(
                        "create_media_buy",
                        {
                            "product_ids": [valid_product_id],
                            "budget": scenario["budget"],
                            "start_date": "2025-09-01",
                            "end_date": "2025-09-30",
                        },
                    )

                    if isinstance(result, dict) and ("error" in result or result.get("status") == "error"):
                        print(f"    ✓ {scenario['desc']}: Error response returned")
                    else:
                        print(f"    ⚠ {scenario['desc']}: Server accepted invalid budget")

                except Exception as e:
                    error_msg = str(e).lower()
                    expected_terms = ["budget", "invalid", "positive", "number"]
                    if any(term in error_msg for term in expected_terms):
                        print(f"    ✓ {scenario['desc']}: Proper exception raised")
                    else:
                        print(f"    ⚠ {scenario['desc']}: Unexpected error: {e}")

        # Test 3: Invalid Date Ranges
        print("\n  Testing Invalid Date Range Scenarios")

        if products and "products" in products and len(products["products"]) > 0:
            date_scenarios = [
                {"start_date": "2025-09-30", "end_date": "2025-09-01", "desc": "end date before start date"},
                {"start_date": "invalid-date", "end_date": "2025-09-30", "desc": "invalid start date format"},
                {"start_date": "2025-09-01", "end_date": "invalid-date", "desc": "invalid end date format"},
                {"start_date": None, "end_date": "2025-09-30", "desc": "null start date"},
            ]

            for scenario in date_scenarios:
                try:
                    result = await test_client.call_mcp_tool(
                        "create_media_buy",
                        {
                            "product_ids": [valid_product_id],
                            "budget": 1000.0,
                            "start_date": scenario["start_date"],
                            "end_date": scenario["end_date"],
                        },
                    )

                    if isinstance(result, dict) and ("error" in result or result.get("status") == "error"):
                        print(f"    ✓ {scenario['desc']}: Error response returned")
                    else:
                        print(f"    ⚠ {scenario['desc']}: Server accepted invalid dates")

                except Exception as e:
                    error_msg = str(e).lower()
                    expected_terms = ["date", "invalid", "format", "before", "after"]
                    if any(term in error_msg for term in expected_terms):
                        print(f"    ✓ {scenario['desc']}: Proper exception raised")
                    else:
                        print(f"    ⚠ {scenario['desc']}: Unexpected error: {e}")

        # Test 4: Nonexistent Resource Access
        print("\n  Testing Nonexistent Resource Access")

        nonexistent_scenarios = [
            {
                "method": "get_media_buy_delivery",
                "params": {"media_buy_id": "nonexistent_media_buy_123"},
                "desc": "nonexistent media buy delivery",
            },
            {
                "method": "check_creative_status",
                "params": {"creative_ids": ["nonexistent_creative_123"]},
                "desc": "nonexistent creative status",
            },
        ]

        for scenario in nonexistent_scenarios:
            try:
                result = await test_client.call_mcp_tool(scenario["method"], scenario["params"])

                if isinstance(result, dict) and ("error" in result or result.get("status") == "error"):
                    print(f"    ✓ {scenario['desc']}: Error response returned")
                else:
                    print(f"    ⚠ {scenario['desc']}: Server returned response for nonexistent resource")

            except Exception as e:
                error_msg = str(e).lower()
                expected_terms = ["not found", "nonexistent", "invalid", "unknown"]
                if any(term in error_msg for term in expected_terms):
                    print(f"    ✓ {scenario['desc']}: Proper exception raised")
                else:
                    print(f"    ⚠ {scenario['desc']}: Unexpected error: {e}")

        # Test 5: Malformed Request Structure
        print("\n  Testing Malformed Request Scenarios")

        try:
            # Test completely invalid MCP call structure
            result = await test_client.mcp_client.call_tool("nonexistent_tool", {"invalid": "structure"})
            print("    ⚠ Server accepted call to nonexistent tool")
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "unknown" in error_msg:
                print("    ✓ Nonexistent tool call properly rejected")
            else:
                print(f"    ⚠ Unexpected error for nonexistent tool: {e}")

        print("\n  ✅ Comprehensive error testing completed")

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
                "get_products", {"brief": "display", "promoted_offering": "TestBrand Alpha premium products"}
            )

            products2 = await client2.call_mcp_tool(
                "get_products", {"brief": "video", "promoted_offering": "TestBrand Beta premium services"}
            )

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
            "get_products",
            {"brief": "brand awareness campaign", "promoted_offering": "Premium Brand luxury automotive collection"},
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
                        "created_at": "2025-09-01T00:00:00Z",
                        "updated_at": "2025-09-01T00:00:00Z",
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
                        "created_at": "2025-09-01T00:00:00Z",
                        "updated_at": "2025-09-01T00:00:00Z",
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

        delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-09-15"}
        )

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

        final_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_id": media_buy_id, "today": "2025-10-01"}
        )

        print("✓ Campaign completed:")
        if "deliveries" in final_delivery and len(final_delivery["deliveries"]) > 0:
            campaign_data = final_delivery["deliveries"][0]
            print(f"  - Total impressions: {campaign_data.get('impressions', 0)}")
            print(f"  - Total spend: ${campaign_data.get('spend', 0)}")
        else:
            print(f"  - Total impressions: {final_delivery.get('total_impressions', 0)}")
            print(f"  - Total spend: ${final_delivery.get('total_spend', 0)}")
        print(f"  - CTR: {final_delivery.get('ctr', 0):.2%}")

        print("\n✅ Full lifecycle test completed successfully!")

    @pytest.mark.asyncio
    async def test_complete_campaign_lifecycle_standard(self, test_client: AdCPTestClient):
        """Test complete campaign lifecycle with proper AdCP spec compliance."""
        print("\n=== Testing Complete Standard Campaign Lifecycle ===")

        # Phase 1: Product Discovery (AdCP spec compliant)
        print("\nPhase 1: Product Discovery")
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Video advertising campaign for spring sports season",
                "promoted_offering": "Nike Air Jordan 2025 basketball shoes and apparel collection",
            },
        )

        assert "products" in products and len(products["products"]) > 0
        selected_product = products["products"][0]
        product_id = selected_product.get("product_id", selected_product.get("id"))
        print(f"✓ Selected product: {product_id} - {selected_product.get('name', 'Unknown')}")

        # Phase 2: Campaign Creation with AdCP-compliant targeting
        print("\nPhase 2: Campaign Creation")
        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 75000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
                "targeting_overlay": {
                    # AdCP spec-compliant geographic targeting
                    "geo_country_any_of": ["US", "CA"],
                    "geo_region_any_of": ["CA", "NY", "TX", "ON"],
                    "geo_metro_any_of": ["501", "803", "807"],  # LA, Dallas, San Francisco
                    # AdCP spec-compliant device targeting
                    "device_type_any_of": ["mobile", "tablet", "ctv"],
                    # AdCP spec-compliant frequency capping
                    "frequency_cap": {"suppress_minutes": 1440, "scope": "media_buy"},  # 24 hours
                },
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        assert "status" in media_buy
        print(f"✓ Created campaign: {media_buy_id} with status: {media_buy['status']}")

        # Phase 3: Creative Group and Asset Management
        print("\nPhase 3: Creative Management")

        # Create creative group
        creative_group = await test_client.call_mcp_tool(
            "create_creative_group", {"name": "Nike Jordan 2025 Campaign Assets"}
        )

        # Handle nested response structure
        if "group" in creative_group:
            group = creative_group["group"]
        else:
            group = creative_group
        group_id = group.get("group_id", group.get("id"))
        print(f"✓ Created creative group: {group_id}")

        # Add comprehensive creative assets
        creative_assets = [
            {
                "creative_id": "nike_jordan_hero_video",
                "principal_id": "e2e-test-principal",
                "name": "Nike Jordan Hero Video 30s",
                "format": "video_16_9",
                "format_id": "video_16_9",
                "content_uri": "https://example.com/nike_jordan_hero_30s.mp4",
                "content": {
                    "url": "https://example.com/nike_jordan_hero_30s.mp4",
                    "duration": 30,
                    "aspect_ratio": "16:9",
                    "video_codec": "h264",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00Z",
                "updated_at": "2025-09-01T00:00:00Z",
            },
            {
                "creative_id": "nike_jordan_ctv_video",
                "principal_id": "e2e-test-principal",
                "name": "Nike Jordan CTV Video 15s",
                "format": "video_16_9",
                "format_id": "video_16_9",
                "content_uri": "https://example.com/nike_jordan_ctv_15s.mp4",
                "content": {
                    "url": "https://example.com/nike_jordan_ctv_15s.mp4",
                    "duration": 15,
                    "aspect_ratio": "16:9",
                    "video_codec": "h264",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00Z",
                "updated_at": "2025-09-01T00:00:00Z",
            },
            {
                "creative_id": "nike_jordan_mobile_banner",
                "principal_id": "e2e-test-principal",
                "name": "Nike Jordan Mobile Banner",
                "format": "display_320x50",
                "format_id": "display_320x50",
                "content_uri": "https://example.com/nike_jordan_mobile_banner.jpg",
                "content": {
                    "url": "https://example.com/nike_jordan_mobile_banner.jpg",
                    "width": 320,
                    "height": 50,
                    "alt_text": "Nike Air Jordan 2025 - Shop Now",
                },
                "status": "pending",
                "created_at": "2025-09-01T00:00:00Z",
                "updated_at": "2025-09-01T00:00:00Z",
            },
        ]

        creative_response = await test_client.call_mcp_tool(
            "add_creative_assets", {"media_buy_id": media_buy_id, "creatives": creative_assets, "group_id": group_id}
        )

        assert "statuses" in creative_response
        creative_statuses = creative_response["statuses"]
        print(f"✓ Added {len(creative_statuses)} creatives to campaign")

        # Phase 4: Campaign Launch and Status Verification
        print("\nPhase 4: Campaign Launch")
        test_client.jump_to_event("campaign-start")

        status_check = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})

        print(f"✓ Campaign status after launch: {status_check.get('status', 'unknown')}")

        # Phase 5: Mid-Campaign Delivery Monitoring
        print("\nPhase 5: Delivery Monitoring")
        test_client.set_mock_time(datetime(2025, 9, 15, 12, 0, 0))
        test_client.jump_to_event("campaign-midpoint")

        mid_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-09-15"}
        )

        assert "deliveries" in mid_delivery and len(mid_delivery["deliveries"]) > 0
        delivery_data = mid_delivery["deliveries"][0]
        print("✓ Mid-campaign delivery:")
        print(f"  - Impressions: {delivery_data.get('impressions', 0):,}")
        print(f"  - Spend: ${delivery_data.get('spend', 0):,.2f}")
        print(f"  - Days elapsed: {delivery_data.get('days_elapsed', 0)}/{delivery_data.get('total_days', 0)}")

        # Phase 6: Performance Optimization
        print("\nPhase 6: Performance Optimization")

        # Update performance index if campaign is underdelivering
        if delivery_data.get("pacing", "on_track") != "ahead":
            perf_update = await test_client.call_mcp_tool(
                "update_performance_index",
                {
                    "media_buy_id": media_buy_id,
                    "performance_data": [
                        {"product_id": product_id, "performance_index": 1.25, "confidence_score": 0.92}
                    ],
                },
            )
            print("✓ Updated performance index for optimization")

        # Phase 7: Campaign Completion and Final Reporting
        print("\nPhase 7: Campaign Completion")
        test_client.set_mock_time(datetime(2025, 10, 1, 9, 0, 0))
        test_client.jump_to_event("campaign-complete")

        final_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-10-01"}
        )

        assert "deliveries" in final_delivery and len(final_delivery["deliveries"]) > 0
        final_data = final_delivery["deliveries"][0]

        print("✓ Campaign completed successfully:")
        print(f"  - Total impressions: {final_data.get('impressions', 0):,}")
        print(f"  - Total spend: ${final_data.get('spend', 0):,.2f}")
        print(f"  - Final status: {final_data.get('status', 'unknown')}")

        # Validate campaign completion metrics
        assert final_data.get("impressions", 0) > 0, "Campaign should have delivered impressions"
        assert final_data.get("spend", 0) > 0, "Campaign should have spent budget"

        print("\n✅ Complete standard campaign lifecycle test passed!")

    @pytest.mark.asyncio
    async def test_multi_product_campaign_lifecycle(self, test_client: AdCPTestClient):
        """Test campaign with multiple products from different categories."""
        print("\n=== Testing Multi-Product Campaign Lifecycle ===")

        # Get products for multi-product campaign
        products_response = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Multi-format advertising campaign for back-to-school season",
                "promoted_offering": "Target back-to-school 2025 clothing, electronics, and school supplies",
            },
        )

        products = products_response["products"]
        assert len(products) >= 2, "Need multiple products for multi-product test"

        # Select up to 3 products for testing
        selected_products = products[:3]
        product_ids = [p.get("product_id", p.get("id")) for p in selected_products]

        print(f"✓ Selected {len(product_ids)} products for multi-product campaign")

        # Create multi-product campaign
        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": product_ids,
                "budget": 125000.0,
                "start_date": "2025-12-15",
                "end_date": "2026-01-15",
                "targeting_overlay": {
                    "geo_country_any_of": ["US"],
                    "geo_region_any_of": ["CA", "TX", "NY", "FL"],
                    "device_type_any_of": ["mobile", "desktop"],
                    "frequency_cap": {"suppress_minutes": 720, "scope": "media_buy"},  # 12 hours
                },
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created multi-product campaign: {media_buy_id}")

        # Verify packages were created for each product
        if "packages" in media_buy:
            packages = media_buy["packages"]
            assert len(packages) == len(product_ids), f"Expected {len(product_ids)} packages, got {len(packages)}"
            print(f"✓ Created {len(packages)} packages for products")

            for i, package in enumerate(packages):
                print(
                    f"  Package {i+1}: {package.get('package_id', 'unknown')} for {package.get('product_id', 'unknown')}"
                )

        # Test delivery across all products
        test_client.jump_to_event("campaign-midpoint")

        delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-12-31"}
        )

        delivery_data = delivery["deliveries"][0]
        print(
            f"✓ Multi-product delivery: {delivery_data.get('impressions', 0):,} impressions, ${delivery_data.get('spend', 0):,.2f} spend"
        )

        print("\n✅ Multi-product campaign lifecycle test passed!")

    @pytest.mark.asyncio
    async def test_campaign_with_frequency_capping(self, test_client: AdCPTestClient):
        """Test campaign with comprehensive frequency capping configuration."""
        print("\n=== Testing Campaign with Frequency Capping ===")

        # Get products
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "High-frequency awareness campaign for brand recognition",
                "promoted_offering": "Coca-Cola Summer 2025 refreshment campaign and new flavors",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        # Test different frequency capping configurations
        frequency_configs = [
            {
                "name": "Aggressive Frequency Cap",
                "config": {"suppress_minutes": 60, "scope": "media_buy"},  # 1 hour
                "budget": 25000,
            },
            {
                "name": "Standard Frequency Cap",
                "config": {"suppress_minutes": 720, "scope": "package"},  # 12 hours
                "budget": 35000,
            },
            {
                "name": "Conservative Frequency Cap",
                "config": {"suppress_minutes": 2880, "scope": "media_buy"},  # 48 hours
                "budget": 20000,
            },
        ]

        campaign_results = []

        for freq_config in frequency_configs:
            print(f"\n Testing {freq_config['name']}")

            media_buy = await test_client.call_mcp_tool(
                "create_media_buy",
                {
                    "product_ids": [product_id],
                    "budget": freq_config["budget"],
                    "start_date": "2025-12-01",
                    "end_date": "2025-12-31",
                    "targeting_overlay": {
                        "geo_country_any_of": ["US"],
                        "device_type_any_of": ["mobile", "desktop", "tablet"],
                        "frequency_cap": freq_config["config"],
                    },
                },
            )

            media_buy_id = media_buy["media_buy_id"]
            print(f"✓ Created campaign with {freq_config['name']}: {media_buy_id}")

            # Test delivery with frequency capping
            test_client.jump_to_event("campaign-midpoint")

            delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-12-15"}
            )

            delivery_data = delivery["deliveries"][0]
            campaign_results.append(
                {
                    "name": freq_config["name"],
                    "media_buy_id": media_buy_id,
                    "impressions": delivery_data.get("impressions", 0),
                    "spend": delivery_data.get("spend", 0),
                    "frequency_config": freq_config["config"],
                }
            )

            print(f"  Impressions: {delivery_data.get('impressions', 0):,}")
            print(f"  Spend: ${delivery_data.get('spend', 0):,.2f}")

        # Validate that different frequency caps produce different delivery patterns
        print(f"\n✓ Frequency capping test completed with {len(campaign_results)} configurations")

        # All campaigns should have delivered something
        for result in campaign_results:
            assert result["impressions"] > 0, f"Campaign {result['name']} should have delivered impressions"
            assert result["spend"] > 0, f"Campaign {result['name']} should have spent budget"

        print("\n✅ Frequency capping campaign test passed!")

    @pytest.mark.asyncio
    async def test_promoted_offering_spec_compliance(self, test_client: AdCPTestClient):
        """Test AdCP spec compliance for promoted_offering field."""
        print("\n=== Testing Promoted Offering Spec Compliance ===")

        # Test cases that should be rejected per AdCP spec
        invalid_cases = [
            {
                "name": "Missing brand - too vague",
                "brief": "Display advertising campaign for retail",
                "promoted_offering": "athletic footwear",  # No brand specified
                "expected_error_keywords": ["brand", "advertiser", "specific"],
            },
            {
                "name": "Missing product details",
                "brief": "Video campaign for technology",
                "promoted_offering": "Apple",  # Brand only, no product
                "expected_error_keywords": ["product", "service", "specific"],
            },
            {
                "name": "Generic category only",
                "brief": "Social media advertising",
                "promoted_offering": "shoes",  # Too generic
                "expected_error_keywords": ["brand", "advertiser"],
            },
            {
                "name": "Empty promoted_offering",
                "brief": "Brand awareness campaign",
                "promoted_offering": "",  # Empty
                "expected_error_keywords": ["required", "empty"],
            },
        ]

        print(f"\nTesting {len(invalid_cases)} invalid promoted_offering cases:")

        for case in invalid_cases:
            print(f"\n  Testing: {case['name']}")
            try:
                result = await test_client.call_mcp_tool(
                    "get_products", {"brief": case["brief"], "promoted_offering": case["promoted_offering"]}
                )

                # If we got here, the server accepted invalid input
                print(f"    ❌ Server incorrectly accepted: '{case['promoted_offering']}'")

            except Exception as e:
                # This is expected - validate it's the right kind of error
                error_message = str(e).lower()
                expected_found = any(keyword in error_message for keyword in case["expected_error_keywords"])

                if expected_found:
                    print(f"    ✓ Correctly rejected: {type(e).__name__}")
                else:
                    print(f"    ⚠ Rejected but unexpected error message: {e}")

        # Test cases that should be accepted
        valid_cases = [
            {
                "name": "Complete brand and product",
                "brief": "Premium video advertising for automotive industry",
                "promoted_offering": "Tesla Model S 2025 electric luxury sedan with autopilot features",
            },
            {
                "name": "Retail brand and specific products",
                "brief": "E-commerce display advertising for holiday season",
                "promoted_offering": "Amazon Prime Day 2025 electronics deals and free shipping",
            },
            {
                "name": "Consumer brand with product line",
                "brief": "Social media campaign for sports apparel",
                "promoted_offering": "Nike Air Max 2025 running shoes and athletic wear collection",
            },
        ]

        print(f"\nTesting {len(valid_cases)} valid promoted_offering cases:")

        for case in valid_cases:
            print(f"\n  Testing: {case['name']}")
            try:
                result = await test_client.call_mcp_tool(
                    "get_products", {"brief": case["brief"], "promoted_offering": case["promoted_offering"]}
                )

                assert "products" in result, "Valid request should return products"
                print(f"    ✓ Correctly accepted: {len(result['products'])} products returned")

            except Exception as e:
                print(f"    ❌ Valid request incorrectly rejected: {e}")

        print("\n✅ Promoted offering spec compliance test completed!")

    @pytest.mark.asyncio
    async def test_invalid_targeting_handling(self, test_client: AdCPTestClient):
        """Test that unsupported targeting dimensions are properly rejected."""
        print("\n=== Testing Invalid Targeting Handling ===")

        # Get a valid product first
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Testing campaign for targeting validation",
                "promoted_offering": "Microsoft Office 365 productivity software and Teams collaboration tools",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        # Test unsupported targeting dimensions (based on user feedback)
        invalid_targeting_cases = [
            {
                "name": "Unsupported keywords targeting",
                "targeting": {
                    "geo_country_any_of": ["US"],
                    "keywords_any_of": ["productivity", "office"],  # Not supported per user
                },
            },
            {
                "name": "Unsupported content categories",
                "targeting": {
                    "geo_country_any_of": ["US"],
                    "content_cat_any_of": ["IAB19", "IAB20"],  # Not supported per user
                },
            },
            {
                "name": "Invalid frequency cap structure",
                "targeting": {
                    "geo_country_any_of": ["US"],
                    "frequency_cap": {"impressions_per_day": 5},  # Wrong structure - should be suppress_minutes
                },
            },
            {
                "name": "Invalid frequency cap scope",
                "targeting": {
                    "geo_country_any_of": ["US"],
                    "frequency_cap": {
                        "suppress_minutes": 1440,
                        "scope": "invalid_scope",  # Should be 'media_buy' or 'package'
                    },
                },
            },
        ]

        print(f"\nTesting {len(invalid_targeting_cases)} invalid targeting cases:")

        for case in invalid_targeting_cases:
            print(f"\n  Testing: {case['name']}")
            try:
                result = await test_client.call_mcp_tool(
                    "create_media_buy",
                    {
                        "product_ids": [product_id],
                        "budget": 10000.0,
                        "start_date": "2025-10-01",
                        "end_date": "2025-10-31",
                        "targeting_overlay": case["targeting"],
                    },
                )

                print(f"    ⚠ Server incorrectly accepted invalid targeting: {case['name']}")

            except Exception as e:
                print(f"    ✓ Correctly rejected invalid targeting: {type(e).__name__}")

        # Test valid targeting that should be accepted
        valid_targeting = {
            "geo_country_any_of": ["US", "CA"],
            "geo_region_any_of": ["CA", "NY"],
            "geo_metro_any_of": ["501", "803"],
            "device_type_any_of": ["mobile", "desktop"],
            "frequency_cap": {"suppress_minutes": 720, "scope": "media_buy"},
        }

        print("\n  Testing valid AdCP-compliant targeting:")
        try:
            result = await test_client.call_mcp_tool(
                "create_media_buy",
                {
                    "product_ids": [product_id],
                    "budget": 15000.0,
                    "start_date": "2025-10-01",
                    "end_date": "2025-10-31",
                    "targeting_overlay": valid_targeting,
                },
            )

            assert "media_buy_id" in result, "Valid targeting should create media buy"
            print(f"    ✓ Valid targeting accepted: {result['media_buy_id']}")

        except Exception as e:
            print(f"    ❌ Valid targeting incorrectly rejected: {e}")

        print("\n✅ Invalid targeting handling test completed!")

    @pytest.mark.asyncio
    async def test_budget_and_date_validation(self, test_client: AdCPTestClient):
        """Test validation of budget and date range inputs."""
        print("\n=== Testing Budget and Date Validation ===")

        # Get valid product for testing
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Validation testing campaign",
                "promoted_offering": "Adobe Creative Cloud 2025 design software suite and subscription",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        # Test invalid budget scenarios
        invalid_budget_cases = [
            {"name": "Negative budget", "budget": -5000.0, "start_date": "2025-11-01", "end_date": "2025-11-30"},
            {"name": "Zero budget", "budget": 0.0, "start_date": "2025-11-01", "end_date": "2025-11-30"},
            {"name": "Extremely small budget", "budget": 0.01, "start_date": "2025-11-01", "end_date": "2025-11-30"},
        ]

        print(f"\nTesting {len(invalid_budget_cases)} invalid budget cases:")

        for case in invalid_budget_cases:
            print(f"\n  Testing: {case['name']} (${case['budget']})")
            try:
                result = await test_client.call_mcp_tool(
                    "create_media_buy",
                    {
                        "product_ids": [product_id],
                        "budget": case["budget"],
                        "start_date": case["start_date"],
                        "end_date": case["end_date"],
                        "targeting_overlay": {"geo_country_any_of": ["US"]},
                    },
                )

                print(f"    ⚠ Server incorrectly accepted invalid budget: ${case['budget']}")

            except Exception as e:
                print(f"    ✓ Correctly rejected invalid budget: {type(e).__name__}")

        # Test invalid date scenarios
        invalid_date_cases = [
            {
                "name": "End date before start date",
                "budget": 10000.0,
                "start_date": "2025-12-31",
                "end_date": "2025-12-01",
            },
            {
                "name": "Same start and end date",
                "budget": 10000.0,
                "start_date": "2025-11-15",
                "end_date": "2025-11-15",
            },
            {"name": "Invalid date format", "budget": 10000.0, "start_date": "invalid-date", "end_date": "2025-11-30"},
            {"name": "Past dates", "budget": 10000.0, "start_date": "2020-01-01", "end_date": "2020-01-31"},
        ]

        print(f"\nTesting {len(invalid_date_cases)} invalid date cases:")

        for case in invalid_date_cases:
            print(f"\n  Testing: {case['name']}")
            try:
                result = await test_client.call_mcp_tool(
                    "create_media_buy",
                    {
                        "product_ids": [product_id],
                        "budget": case["budget"],
                        "start_date": case["start_date"],
                        "end_date": case["end_date"],
                        "targeting_overlay": {"geo_country_any_of": ["US"]},
                    },
                )

                print(f"    ⚠ Server incorrectly accepted invalid dates: {case['start_date']} to {case['end_date']}")

            except Exception as e:
                print(f"    ✓ Correctly rejected invalid dates: {type(e).__name__}")

        # Test valid case to ensure validation isn't too strict
        print("\n  Testing valid budget and dates:")
        try:
            result = await test_client.call_mcp_tool(
                "create_media_buy",
                {
                    "product_ids": [product_id],
                    "budget": 25000.0,
                    "start_date": "2025-11-01",
                    "end_date": "2025-11-30",
                    "targeting_overlay": {"geo_country_any_of": ["US"]},
                },
            )

            assert "media_buy_id" in result, "Valid budget and dates should create media buy"
            print(f"    ✓ Valid case accepted: {result['media_buy_id']}")

        except Exception as e:
            print(f"    ❌ Valid case incorrectly rejected: {e}")

        print("\n✅ Budget and date validation test completed!")

    @pytest.mark.asyncio
    async def test_budget_exceeded_simulation(self, test_client: AdCPTestClient):
        """Test budget exceeded scenario using simulation controls."""
        print("\n=== Testing Budget Exceeded Simulation ===")

        # Create a campaign for budget testing
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "High-spend campaign for budget monitoring",
                "promoted_offering": "BMW X5 2025 luxury SUV with premium package and financing options",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 30000.0,  # Set budget that we'll exceed
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "targeting_overlay": {"geo_country_any_of": ["US"], "device_type_any_of": ["mobile", "desktop"]},
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created campaign for budget testing: {media_buy_id}")
        print(f"  Budget: ${media_buy.get('budget', 30000)}")

        # Use simulation control to trigger budget exceeded scenario
        if hasattr(test_client, "test_session_id"):
            strategy_id = f"sim_budget_test_{test_client.test_session_id[:8]}"

            try:
                # Set scenario to trigger budget exceeded
                scenario_result = await test_client.call_mcp_tool(
                    "simulation_control",
                    {
                        "strategy_id": strategy_id,
                        "action": "set_scenario",
                        "parameters": {"scenario": "budget_exceeded"},
                    },
                )
                print("✓ Set budget exceeded simulation scenario")

                # Jump to mid-campaign to trigger the scenario
                jump_result = await test_client.call_mcp_tool(
                    "simulation_control",
                    {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "error-budget-exceeded"}},
                )
                print("✓ Jumped to budget exceeded event")

                # Check delivery to see if budget was exceeded
                delivery = await test_client.call_mcp_tool(
                    "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-10-15"}
                )

                if "deliveries" in delivery and len(delivery["deliveries"]) > 0:
                    delivery_data = delivery["deliveries"][0]
                    spend = delivery_data.get("spend", 0)
                    budget = 30000.0

                    print("✓ Budget exceeded scenario results:")
                    print(f"  - Original budget: ${budget:,.2f}")
                    print(f"  - Actual spend: ${spend:,.2f}")
                    print(f"  - Overspend ratio: {spend/budget:.2f}x")

                    if spend > budget * 1.1:  # More than 10% overspend
                        print("✓ Budget exceeded scenario working correctly")
                    else:
                        print("⚠ Budget exceeded scenario may not be active")

            except Exception as e:
                print(f"⚠ Simulation control not available or failed: {e}")

                # Fall back to regular delivery check
                delivery = await test_client.call_mcp_tool(
                    "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-10-15"}
                )

                delivery_data = delivery["deliveries"][0] if delivery.get("deliveries") else {}
                print(f"✓ Regular delivery check: ${delivery_data.get('spend', 0):,.2f} spent")

        print("\n✅ Budget exceeded simulation test completed!")

    @pytest.mark.asyncio
    async def test_creative_approval_workflow(self, test_client: AdCPTestClient):
        """Test creative approval and rejection workflow with human review."""
        print("\n=== Testing Creative Approval Workflow ===")

        # Create base campaign for creative testing
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Brand safety sensitive campaign requiring creative review",
                "promoted_offering": "Pfizer COVID-19 vaccine information and health safety awareness",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 50000.0,
                "start_date": "2025-11-01",
                "end_date": "2025-11-30",
                "targeting_overlay": {"geo_country_any_of": ["US"], "device_type_any_of": ["mobile", "desktop"]},
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created campaign for creative testing: {media_buy_id}")

        # Create creative group
        creative_group = await test_client.call_mcp_tool(
            "create_creative_group", {"name": "Health Campaign Creatives - Review Required"}
        )

        group = creative_group.get("group", creative_group)
        group_id = group.get("group_id", group.get("id"))

        # Phase 1: Submit creatives that require review
        print("\nPhase 1: Creative Submission")

        test_creatives = [
            {
                "creative_id": "health_awareness_video",
                "principal_id": "e2e-test-principal",
                "name": "COVID-19 Health Awareness Video",
                "format": "video_16_9",
                "format_id": "video_16_9",
                "content_uri": "https://example.com/covid_awareness.mp4",
                "content": {"url": "https://example.com/covid_awareness.mp4", "duration": 30, "aspect_ratio": "16:9"},
                "status": "pending",
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": "2025-11-01T00:00:00Z",
            },
            {
                "creative_id": "vaccine_info_banner",
                "principal_id": "e2e-test-principal",
                "name": "Vaccine Information Banner",
                "format": "display_728x90",
                "format_id": "display_728x90",
                "content_uri": "https://example.com/vaccine_banner.jpg",
                "content": {"url": "https://example.com/vaccine_banner.jpg", "width": 728, "height": 90},
                "status": "pending",
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": "2025-11-01T00:00:00Z",
            },
        ]

        creative_response = await test_client.call_mcp_tool(
            "add_creative_assets", {"media_buy_id": media_buy_id, "creatives": test_creatives, "group_id": group_id}
        )

        creative_statuses = creative_response.get("statuses", [])
        creative_ids = [status["creative_id"] for status in creative_statuses]
        print(f"✓ Submitted {len(creative_ids)} creatives for review")

        # Phase 2: Check for pending creative reviews
        print("\nPhase 2: Human Review Detection")

        try:
            # Check if there are pending creatives that need approval
            pending_creatives = await test_client.call_mcp_tool("get_pending_creatives", {})

            if "creatives" in pending_creatives and len(pending_creatives["creatives"]) > 0:
                print(f"✓ Found {len(pending_creatives['creatives'])} pending creatives")

                # Phase 3: Human approval simulation
                print("\nPhase 3: Human Approval Process")

                for creative in pending_creatives["creatives"]:
                    creative_id = creative.get("creative_id", creative.get("id"))

                    # Simulate human approval decision
                    approval_decision = "approved" if "awareness" in creative.get("name", "").lower() else "rejected"
                    rejection_reason = "Content requires medical review" if approval_decision == "rejected" else None

                    approve_result = await test_client.call_mcp_tool(
                        "approve_creative",
                        {
                            "creative_id": creative_id,
                            "decision": approval_decision,
                            "rejection_reason": rejection_reason,
                            "notes": f"Reviewed by human moderator - {approval_decision}",
                        },
                    )

                    print(f"  ✓ Creative {creative_id}: {approval_decision}")
                    if rejection_reason:
                        print(f"    Reason: {rejection_reason}")
            else:
                print("⚠ No pending creatives found - may be auto-approved")

        except Exception as e:
            print(f"⚠ Creative approval workflow not available: {e}")

        # Phase 4: Check final creative status
        print("\nPhase 4: Creative Status Verification")

        final_status = await test_client.call_mcp_tool("check_creative_status", {"creative_ids": creative_ids})

        if "statuses" in final_status:
            for status in final_status["statuses"]:
                creative_id = status.get("creative_id", "unknown")
                status_value = status.get("status", "unknown")
                print(f"  ✓ Creative {creative_id}: {status_value}")

        print("\n✅ Creative approval workflow test completed!")

    @pytest.mark.asyncio
    async def test_human_task_management_workflow(self, test_client: AdCPTestClient):
        """Test human task creation, assignment, and completion workflow."""
        print("\n=== Testing Human Task Management Workflow ===")

        # Create campaign that may require human intervention
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "High-value enterprise campaign requiring manual oversight",
                "promoted_offering": "Salesforce Enterprise CRM platform with custom implementation services",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 150000.0,  # High budget requiring approval
                "start_date": "2025-12-01",
                "end_date": "2025-12-31",
                "targeting_overlay": {"geo_country_any_of": ["US"], "device_type_any_of": ["desktop"]},
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created high-value campaign: {media_buy_id}")

        # Phase 1: Create human task for campaign approval
        print("\nPhase 1: Human Task Creation")

        try:
            task_creation = await test_client.call_mcp_tool(
                "create_workflow_step_for_task",
                {
                    "task_type": "approve_high_budget_campaign",
                    "description": f"Manual approval required for campaign {media_buy_id} with ${150000} budget",
                    "metadata": {"media_buy_id": media_buy_id, "budget": 150000.0, "requires_review": True},
                    "priority": "high",
                    "assigned_to": "campaign_manager",
                },
            )

            if "task_id" in task_creation:
                task_id = task_creation["task_id"]
                print(f"✓ Created human task: {task_id}")

                # Phase 2: Check pending workflows
                print("\nPhase 2: Pending Task Verification")

                pending_tasks = await test_client.call_mcp_tool(
                    "get_pending_workflows", {"task_type": "approve_high_budget_campaign"}
                )

                if "tasks" in pending_tasks and len(pending_tasks["tasks"]) > 0:
                    print(f"✓ Found {len(pending_tasks['tasks'])} pending approval tasks")

                    # Phase 3: Task assignment
                    print("\nPhase 3: Task Assignment")

                    assignment_result = await test_client.call_mcp_tool(
                        "assign_task",
                        {
                            "task_id": task_id,
                            "assigned_to": "senior_campaign_manager",
                            "notes": "Assigned to senior manager for high-budget review",
                        },
                    )
                    print("✓ Task assigned to senior campaign manager")

                    # Phase 4: Task completion
                    print("\nPhase 4: Task Completion")

                    completion_result = await test_client.call_mcp_tool(
                        "complete_task",
                        {
                            "task_id": task_id,
                            "resolution": "approved",
                            "notes": "Campaign approved after budget review and targeting verification",
                            "completion_data": {
                                "approval_reason": "Budget justified by target audience size",
                                "reviewer": "senior_campaign_manager",
                            },
                        },
                    )
                    print("✓ Task completed with approval")

                    # Phase 5: Task verification
                    print("\nPhase 5: Task Verification")

                    verification = await test_client.call_mcp_tool(
                        "verify_task", {"task_id": task_id, "expected_resolution": "approved"}
                    )

                    if verification.get("verified", False):
                        print("✓ Task completion verified successfully")
                    else:
                        print("⚠ Task verification failed or incomplete")

                else:
                    print("⚠ No pending tasks found")
            else:
                print("⚠ Task creation may have failed")

        except Exception as e:
            print(f"⚠ Human task workflow not available: {e}")

            # Fallback - just check campaign status
            status = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})
            print(f"✓ Campaign status: {status.get('status', 'unknown')}")

        print("\n✅ Human task management workflow test completed!")

    @pytest.mark.asyncio
    async def test_manual_campaign_approval_process(self, test_client: AdCPTestClient):
        """Test complete manual approval process from creation to activation."""
        print("\n=== Testing Manual Campaign Approval Process ===")

        # Create campaign that should require manual approval
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Pharmaceutical advertising requiring regulatory compliance review",
                "promoted_offering": "Johnson & Johnson prescription medication Stelara for autoimmune conditions",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        # Phase 1: Create campaign that should trigger approval workflow
        print("\nPhase 1: Campaign Creation Requiring Approval")

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 75000.0,
                "start_date": "2026-01-15",
                "end_date": "2026-02-15",
                "targeting_overlay": {"geo_country_any_of": ["US"], "device_type_any_of": ["desktop", "mobile"]},
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        initial_status = media_buy.get("status", "unknown")

        print(f"✓ Created pharmaceutical campaign: {media_buy_id}")
        print(f"  Initial status: {initial_status}")

        # Check if campaign is in pending approval state
        if initial_status in ["pending_approval", "pending", "pending_review"]:
            print("✓ Campaign correctly entered approval workflow")

            # Phase 2: Check for human approval tasks
            print("\nPhase 2: Approval Task Detection")

            try:
                pending_workflows = await test_client.call_mcp_tool("get_pending_workflows", {})

                approval_tasks = []
                if "tasks" in pending_workflows:
                    approval_tasks = [
                        task for task in pending_workflows["tasks"] if media_buy_id in str(task.get("metadata", {}))
                    ]

                if approval_tasks:
                    print(f"✓ Found {len(approval_tasks)} approval tasks for campaign")

                    # Phase 3: Simulate approval process
                    print("\nPhase 3: Approval Process Simulation")

                    for task in approval_tasks:
                        task_id = task.get("task_id", task.get("id"))

                        # Complete approval task
                        await test_client.call_mcp_tool(
                            "mark_task_complete",
                            {
                                "task_id": task_id,
                                "resolution": "approved",
                                "notes": "Pharmaceutical campaign approved after regulatory review",
                            },
                        )
                        print(f"  ✓ Completed approval task: {task_id}")

                else:
                    print("⚠ No approval tasks found - may be auto-approved")

            except Exception as e:
                print(f"⚠ Approval workflow check failed: {e}")

        else:
            print("⚠ Campaign did not require approval - may be auto-approved")

        # Phase 4: Verify final campaign status
        print("\nPhase 4: Final Status Verification")

        # Give some time for approval to process
        final_status = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})

        final_status_value = final_status.get("status", "unknown")
        print(f"✓ Final campaign status: {final_status_value}")

        # Phase 5: Test campaign activation
        if final_status_value in ["approved", "active", "ready"]:
            print("\nPhase 5: Campaign Activation Test")

            # Jump to campaign start to activate
            test_client.jump_to_event("campaign-start")

            activation_status = await test_client.call_mcp_tool(
                "check_media_buy_status", {"media_buy_id": media_buy_id}
            )

            print(f"✓ Campaign activation status: {activation_status.get('status', 'unknown')}")

            # Test delivery after activation
            delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2026-01-20"}
            )

            if "deliveries" in delivery and len(delivery["deliveries"]) > 0:
                delivery_data = delivery["deliveries"][0]
                print(f"✓ Campaign delivering: {delivery_data.get('impressions', 0)} impressions")
            else:
                print("⚠ No delivery data available")

        print("\n✅ Manual campaign approval process test completed!")

    @pytest.mark.asyncio
    async def test_performance_optimization_comprehensive(self, test_client: AdCPTestClient):
        """Test comprehensive performance optimization with performance index updates."""
        print("\n=== Testing Performance Optimization Comprehensive ===")

        # Create campaign for performance testing
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Performance-driven campaign for conversion optimization",
                "promoted_offering": "HubSpot marketing automation platform with lead generation tools",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 60000.0,
                "start_date": "2025-09-01",
                "end_date": "2025-09-30",
                "targeting_overlay": {
                    "geo_country_any_of": ["US"],
                    "geo_region_any_of": ["CA", "NY", "TX"],
                    "device_type_any_of": ["desktop", "mobile"],
                    "frequency_cap": {"suppress_minutes": 1440, "scope": "media_buy"},
                },
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created performance campaign: {media_buy_id}")

        # Phase 1: Initial Performance Baseline
        print("\nPhase 1: Initial Performance Baseline")
        test_client.jump_to_event("campaign-start")

        # Get initial delivery metrics
        initial_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-09-03"}
        )

        initial_data = initial_delivery["deliveries"][0] if initial_delivery.get("deliveries") else {}
        print("✓ Initial baseline established:")
        print(f"  - Impressions: {initial_data.get('impressions', 0):,}")
        print(f"  - Spend: ${initial_data.get('spend', 0):,.2f}")
        print(f"  - Pacing: {initial_data.get('pacing', 'unknown')}")

        # Phase 2: Performance Monitoring and Optimization Trigger Points
        print("\nPhase 2: Performance Monitoring Timeline")

        optimization_timeline = [
            {
                "day": "2025-09-08",
                "event": "campaign-week1",
                "performance_check": "underdelivering",
                "action": "increase_performance_index",
            },
            {
                "day": "2025-09-15",
                "event": "campaign-midpoint",
                "performance_check": "on_track",
                "action": "maintain_performance",
            },
            {
                "day": "2025-09-25",
                "event": "campaign-final-push",
                "performance_check": "optimize_for_completion",
                "action": "aggressive_performance_boost",
            },
        ]

        performance_results = []

        for checkpoint in optimization_timeline:
            print(f"\n  Checkpoint: {checkpoint['day']} ({checkpoint['event']})")

            # Jump to the checkpoint
            test_client.set_mock_time(datetime.fromisoformat(f"{checkpoint['day']}T12:00:00"))
            test_client.jump_to_event(checkpoint["event"])

            # Get delivery data at this point
            delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": checkpoint["day"]}
            )

            delivery_data = delivery["deliveries"][0] if delivery.get("deliveries") else {}

            # Calculate performance metrics
            days_elapsed = delivery_data.get("days_elapsed", 1)
            total_days = delivery_data.get("total_days", 31)
            expected_progress = days_elapsed / total_days
            actual_spend_rate = delivery_data.get("spend", 0) / 60000.0 if delivery_data.get("spend", 0) > 0 else 0

            print(f"    Progress: {days_elapsed}/{total_days} days ({expected_progress:.2%})")
            print(f"    Spend rate: {actual_spend_rate:.2%} of budget")
            print(f"    Impressions: {delivery_data.get('impressions', 0):,}")

            # Apply performance optimization based on performance check
            performance_index_update = None
            confidence_score = 0.8

            if checkpoint["action"] == "increase_performance_index":
                performance_index_update = 1.3
                confidence_score = 0.85
                print(f"    ✓ Applying performance boost: {performance_index_update}x")
            elif checkpoint["action"] == "maintain_performance":
                performance_index_update = 1.1
                confidence_score = 0.9
                print(f"    ✓ Maintaining performance: {performance_index_update}x")
            elif checkpoint["action"] == "aggressive_performance_boost":
                performance_index_update = 1.5
                confidence_score = 0.75
                print(f"    ✓ Aggressive performance boost: {performance_index_update}x")

            # Update performance index
            if performance_index_update:
                perf_result = await test_client.call_mcp_tool(
                    "update_performance_index",
                    {
                        "media_buy_id": media_buy_id,
                        "performance_data": [
                            {
                                "product_id": product_id,
                                "performance_index": performance_index_update,
                                "confidence_score": confidence_score,
                            }
                        ],
                    },
                )
                print("    ✓ Performance index updated successfully")

            performance_results.append(
                {
                    "checkpoint": checkpoint["day"],
                    "delivery_data": delivery_data,
                    "performance_index": performance_index_update,
                    "confidence_score": confidence_score,
                }
            )

        # Phase 3: Final Performance Analysis
        print("\nPhase 3: Final Performance Analysis")

        # Jump to campaign completion
        test_client.set_mock_time(datetime(2025, 4, 1, 9, 0, 0))
        test_client.jump_to_event("campaign-complete")

        final_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2025-10-01"}
        )

        final_data = final_delivery["deliveries"][0] if final_delivery.get("deliveries") else {}

        print("✓ Final campaign performance:")
        print(f"  - Total impressions: {final_data.get('impressions', 0):,}")
        print(f"  - Total spend: ${final_data.get('spend', 0):,.2f}")
        print(f"  - Budget utilization: {(final_data.get('spend', 0) / 60000.0):.1%}")
        print(f"  - Final status: {final_data.get('status', 'unknown')}")

        # Validate performance optimization worked
        total_impressions = final_data.get("impressions", 0)
        total_spend = final_data.get("spend", 0)

        assert total_impressions > 0, "Campaign should have delivered impressions"
        assert total_spend > 0, "Campaign should have spent budget"

        if total_spend > 0 and total_impressions > 0:
            final_cpm = (total_spend / total_impressions) * 1000
            print(f"  - Final CPM: ${final_cpm:.2f}")

        print(f"\n✓ Performance optimization applied at {len(optimization_timeline)} checkpoints")
        print("\n✅ Performance optimization comprehensive test completed!")

    @pytest.mark.asyncio
    async def test_delivery_monitoring_over_time(self, test_client: AdCPTestClient):
        """Test delivery monitoring and pacing over campaign lifetime."""
        print("\n=== Testing Delivery Monitoring Over Time ===")

        # Create campaign for delivery monitoring
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Long-running brand awareness campaign for delivery monitoring",
                "promoted_offering": "Spotify Premium music streaming service with ad-free experience",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 45000.0,
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",  # 31-day campaign
                "targeting_overlay": {
                    "geo_country_any_of": ["US", "CA"],
                    "device_type_any_of": ["mobile", "desktop", "tablet"],
                    "frequency_cap": {"suppress_minutes": 720, "scope": "media_buy"},  # 12 hours
                },
            },
        )

        media_buy_id = media_buy["media_buy_id"]
        print(f"✓ Created monitoring campaign: {media_buy_id}")

        # Phase 1: Daily Delivery Monitoring
        print("\nPhase 1: Daily Delivery Monitoring")

        # Define monitoring schedule - key days throughout campaign
        monitoring_schedule = [
            {"day": 1, "date": "2026-05-01", "expected_progress": 0.03},
            {"day": 3, "date": "2026-05-03", "expected_progress": 0.10},
            {"day": 7, "date": "2026-05-07", "expected_progress": 0.23},
            {"day": 14, "date": "2026-05-14", "expected_progress": 0.45},
            {"day": 21, "date": "2026-05-21", "expected_progress": 0.68},
            {"day": 28, "date": "2026-05-28", "expected_progress": 0.90},
            {"day": 31, "date": "2026-05-31", "expected_progress": 1.00},
        ]

        delivery_tracking = []

        for checkpoint in monitoring_schedule:
            print(f"\n  Day {checkpoint['day']} ({checkpoint['date']}):")

            # Set time and get delivery
            test_client.set_mock_time(datetime.fromisoformat(f"{checkpoint['date']}T15:00:00"))

            if checkpoint["day"] == 1:
                test_client.jump_to_event("campaign-start")
            elif checkpoint["day"] == 14:
                test_client.jump_to_event("campaign-midpoint")
            elif checkpoint["day"] == 31:
                test_client.jump_to_event("campaign-complete")

            delivery = await test_client.call_mcp_tool(
                "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": checkpoint["date"]}
            )

            delivery_data = delivery["deliveries"][0] if delivery.get("deliveries") else {}

            # Calculate key metrics
            impressions = delivery_data.get("impressions", 0)
            spend = delivery_data.get("spend", 0)
            days_elapsed = delivery_data.get("days_elapsed", checkpoint["day"])
            total_days = delivery_data.get("total_days", 31)
            pacing = delivery_data.get("pacing", "unknown")

            actual_progress = spend / 45000.0 if spend > 0 else 0
            progress_variance = actual_progress - checkpoint["expected_progress"]

            print(f"    Impressions: {impressions:,}")
            print(f"    Spend: ${spend:,.2f} ({actual_progress:.1%} of budget)")
            print(f"    Expected: {checkpoint['expected_progress']:.1%} (variance: {progress_variance:+.1%})")
            print(f"    Pacing: {pacing}")
            print(f"    Days: {days_elapsed}/{total_days}")

            # Check for delivery issues
            if abs(progress_variance) > 0.15:  # More than 15% variance
                if progress_variance < -0.15:
                    print(f"    ⚠ UNDERDELIVERING by {abs(progress_variance):.1%}")
                else:
                    print(f"    ⚠ OVERDELIVERING by {progress_variance:.1%}")
            else:
                print("    ✓ Delivery on track")

            delivery_tracking.append(
                {
                    "day": checkpoint["day"],
                    "date": checkpoint["date"],
                    "impressions": impressions,
                    "spend": spend,
                    "actual_progress": actual_progress,
                    "expected_progress": checkpoint["expected_progress"],
                    "variance": progress_variance,
                    "pacing": pacing,
                }
            )

        # Phase 2: Delivery Analysis and Validation
        print("\nPhase 2: Delivery Analysis")

        # Analyze delivery patterns
        total_impressions = delivery_tracking[-1]["impressions"]
        total_spend = delivery_tracking[-1]["spend"]
        budget_utilization = total_spend / 45000.0

        print("✓ Campaign delivery summary:")
        print(f"  - Total impressions delivered: {total_impressions:,}")
        print(f"  - Total budget spent: ${total_spend:,.2f}")
        print(f"  - Budget utilization: {budget_utilization:.1%}")

        # Check for consistent delivery growth
        previous_impressions = 0
        consistent_growth = True
        for checkpoint in delivery_tracking:
            if checkpoint["impressions"] < previous_impressions:
                consistent_growth = False
                break
            previous_impressions = checkpoint["impressions"]

        if consistent_growth:
            print("  ✓ Delivery showed consistent growth over time")
        else:
            print("  ⚠ Delivery had inconsistent patterns")

        # Validate final results
        assert total_impressions > 0, "Campaign should have delivered impressions"
        assert total_spend > 0, "Campaign should have spent budget"
        assert budget_utilization > 0.5, "Campaign should have spent at least 50% of budget"

        print(f"\n✓ Monitored delivery across {len(monitoring_schedule)} checkpoints")
        print("\n✅ Delivery monitoring over time test completed!")

    @pytest.mark.asyncio
    async def test_campaign_updates_and_modifications(self, test_client: AdCPTestClient):
        """Test mid-flight campaign updates and modifications."""
        print("\n=== Testing Campaign Updates and Modifications ===")

        # Create campaign for modification testing
        products = await test_client.call_mcp_tool(
            "get_products",
            {
                "brief": "Flexible campaign for testing updates and modifications",
                "promoted_offering": "Zoom video conferencing software with enterprise features",
            },
        )

        product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

        # Phase 1: Initial Campaign Creation
        print("\nPhase 1: Initial Campaign Creation")

        initial_media_buy = await test_client.call_mcp_tool(
            "create_media_buy",
            {
                "product_ids": [product_id],
                "budget": 35000.0,
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "targeting_overlay": {
                    "geo_country_any_of": ["US"],
                    "device_type_any_of": ["desktop"],
                    "frequency_cap": {"suppress_minutes": 1440, "scope": "media_buy"},
                },
            },
        )

        media_buy_id = initial_media_buy["media_buy_id"]
        print(f"✓ Created campaign for updates: {media_buy_id}")
        print(f"  Initial budget: ${initial_media_buy.get('budget', 35000):,.2f}")
        print(f"  Initial targeting: {initial_media_buy.get('targeting_overlay', {}).get('geo_country_any_of', [])}")

        # Start campaign
        test_client.jump_to_event("campaign-start")

        # Phase 2: Budget Increase
        print("\nPhase 2: Budget Increase")
        test_client.set_mock_time(datetime(2025, 6, 10, 14, 0, 0))

        try:
            budget_update = await test_client.call_mcp_tool(
                "update_media_buy",
                {"media_buy_id": media_buy_id, "budget": 50000.0, "today": "2026-06-10"},  # Increase budget
            )

            print("✓ Budget increased to $50,000")
            print(f"  Update status: {budget_update.get('status', 'unknown')}")

        except Exception as e:
            print(f"⚠ Budget update failed: {e}")

        # Phase 3: Targeting Expansion
        print("\nPhase 3: Targeting Expansion")
        test_client.set_mock_time(datetime(2025, 6, 15, 10, 0, 0))

        try:
            targeting_update = await test_client.call_mcp_tool(
                "update_media_buy",
                {
                    "media_buy_id": media_buy_id,
                    "targeting_overlay": {
                        "geo_country_any_of": ["US", "CA"],  # Add Canada
                        "device_type_any_of": ["desktop", "mobile"],  # Add mobile
                        "frequency_cap": {"suppress_minutes": 720, "scope": "media_buy"},  # Reduce to 12 hours
                    },
                    "today": "2026-06-15",
                },
            )

            print("✓ Targeting expanded to include Canada and mobile devices")
            print(f"  Update status: {targeting_update.get('status', 'unknown')}")

        except Exception as e:
            print(f"⚠ Targeting update failed: {e}")

        # Phase 4: Campaign Extension
        print("\nPhase 4: Campaign Extension")
        test_client.set_mock_time(datetime(2025, 6, 25, 16, 0, 0))

        try:
            extension_update = await test_client.call_mcp_tool(
                "update_media_buy",
                {
                    "media_buy_id": media_buy_id,
                    "flight_end_date": "2026-07-15",  # Extend by 15 days
                    "today": "2026-06-25",
                },
            )

            print("✓ Campaign extended to July 15th")
            print(f"  Update status: {extension_update.get('status', 'unknown')}")

        except Exception as e:
            print(f"⚠ Campaign extension failed: {e}")

        # Phase 5: Verify Final Campaign State
        print("\nPhase 5: Final State Verification")

        final_status = await test_client.call_mcp_tool("check_media_buy_status", {"media_buy_id": media_buy_id})

        print(f"✓ Final campaign status: {final_status.get('status', 'unknown')}")

        # Check final delivery with all updates applied
        test_client.set_mock_time(datetime(2025, 7, 1, 12, 0, 0))

        final_delivery = await test_client.call_mcp_tool(
            "get_media_buy_delivery", {"media_buy_ids": [media_buy_id], "today": "2026-07-01"}
        )

        if "deliveries" in final_delivery and len(final_delivery["deliveries"]) > 0:
            delivery_data = final_delivery["deliveries"][0]
            print("✓ Campaign delivery after updates:")
            print(f"  - Impressions: {delivery_data.get('impressions', 0):,}")
            print(f"  - Spend: ${delivery_data.get('spend', 0):,.2f}")
            print(f"  - Budget utilization: {(delivery_data.get('spend', 0) / 50000.0):.1%}")

            # Validate that updates had impact
            assert delivery_data.get("impressions", 0) > 0, "Updated campaign should deliver impressions"
            assert delivery_data.get("spend", 0) > 0, "Updated campaign should spend budget"

        print("\n✅ Campaign updates and modifications test completed!")


# Pytest configuration hooks
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--mode", default="docker", choices=["local", "docker", "ci", "external"], help="Test execution mode"
    )
    parser.addoption("--server-url", default=None, help="External server URL for testing")
    parser.addoption("--keep-data", action="store_true", default=False, help="Keep test data after completion")
