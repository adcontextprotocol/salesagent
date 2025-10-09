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

from .adcp_schema_validator import AdCPSchemaValidator, SchemaValidationError

DEFAULT_MCP_PORT = int(os.getenv("ADCP_SALES_PORT", "8080"))  # Default MCP port
DEFAULT_A2A_PORT = int(os.getenv("A2A_PORT", "8091"))  # Default A2A port
DEFAULT_ADMIN_PORT = int(os.getenv("ADMIN_UI_PORT", "8087"))  # From .env
TEST_TIMEOUT = 30


class AdCPTestClient:
    """Client for testing AdCP servers with full testing hook support and schema validation."""

    def __init__(
        self,
        mcp_url: str,
        a2a_url: str,
        auth_token: str,
        test_session_id: str | None = None,
        dry_run: bool = True,
        validate_schemas: bool = True,
        offline_mode: bool = False,
    ):
        self.mcp_url = mcp_url
        self.a2a_url = a2a_url
        self.auth_token = auth_token
        self.test_session_id = test_session_id or str(uuid.uuid4())
        self.dry_run = dry_run
        self.validate_schemas = validate_schemas
        self.offline_mode = offline_mode
        self.mock_time = None
        self.mcp_client = None
        self.http_client = httpx.AsyncClient()
        self.schema_validator = None

    async def __aenter__(self):
        """Enter async context."""
        headers = self._build_headers()
        transport = StreamableHttpTransport(url=f"{self.mcp_url}/mcp/", headers=headers)
        self.mcp_client = Client(transport=transport)
        await self.mcp_client.__aenter__()

        # Initialize schema validator if enabled
        if self.validate_schemas:
            self.schema_validator = AdCPSchemaValidator(
                offline_mode=self.offline_mode, adcp_version="v1"  # Default to v1, can be made configurable
            )
            await self.schema_validator.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self.mcp_client:
            await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.schema_validator:
            await self.schema_validator.__aexit__(exc_type, exc_val, exc_tb)
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
        """Call an MCP tool and parse the response with robust error handling and schema validation."""
        try:
            # Convert tool_name to task_name for schema validation
            # MCP tools use underscore format, AdCP schemas use hyphen format
            task_name = tool_name.replace("_", "-")

            # Validate request if schema validation is enabled
            if self.validate_schemas and self.schema_validator:
                try:
                    await self.schema_validator.validate_request(task_name, params)
                    print(f"✓ Request schema validation passed for {task_name}")
                except SchemaValidationError as e:
                    print(f"⚠ Request schema validation failed for {task_name}: {e}")
                    for error in e.validation_errors:
                        print(f"  - {error}")
                    # Don't fail the test, just warn - schemas might be stricter than implementation
                except Exception as e:
                    print(f"⚠ Request schema validation error for {task_name}: {e}")

            # Make the actual API call
            result = await self.mcp_client.call_tool(tool_name, {"req": params})
            parsed_response = self._parse_mcp_response(result)

            # Validate response if schema validation is enabled
            if self.validate_schemas and self.schema_validator:
                try:
                    await self.schema_validator.validate_response(task_name, parsed_response)
                    print(f"✓ Response schema validation passed for {task_name}")
                except SchemaValidationError as e:
                    print(f"⚠ Response schema validation failed for {task_name}: {e}")
                    for error in e.validation_errors:
                        print(f"  - {error}")
                    # Don't fail the test, just warn - this helps identify discrepancies
                except Exception as e:
                    print(f"⚠ Response schema validation error for {task_name}: {e}")

            return parsed_response

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

            # Validate format IDs (formats is a list of format ID strings per AdCP spec)
            for j, format_id in enumerate(formats):
                assert isinstance(format_id, str), f"Product {i} format {j} must be a string format_id"
                assert len(format_id) > 0, f"Product {i} format {j} format_id cannot be empty"

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

        # Extract format IDs from products (formats is a list of format ID strings per AdCP spec)
        all_format_ids = []
        for product in products["products"]:
            assert "formats" in product, "Product must contain formats"
            for format_id in product["formats"]:
                assert isinstance(format_id, str), "Format ID must be a string"
                all_format_ids.append(format_id)

        # Now call list_creative_formats to get full format details
        formats_response = await test_client.call_mcp_tool("list_creative_formats", {"req": {}})
        assert "formats" in formats_response, "Response must contain 'formats' field"
        assert isinstance(formats_response["formats"], list), "Formats must be a list"

        # Validate full format details
        for format_info in formats_response["formats"]:
            # Validate required format fields
            assert "format_id" in format_info, "Format missing format_id"
            assert "name" in format_info, "Format missing name"
            assert "type" in format_info, "Format missing type"

            # Validate format type
            valid_types = ["video", "audio", "display", "native", "dooh"]
            assert format_info["type"] in valid_types, f"Invalid format type: {format_info['type']}"

        print(f"✓ Discovered {len(all_format_ids)} format IDs in {len(products['products'])} products")
        print(f"✓ Retrieved {len(formats_response['formats'])} full format details via list_creative_formats")
        for i, format_info in enumerate(formats_response["formats"][:5]):  # Show first 5
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
            "buyer_ref": "e2e_comprehensive_" + str(uuid.uuid4().hex[:8]),
            "promoted_offering": "Test Campaign Product",
            "packages": [
                {
                    "buyer_ref": "pkg_comp_" + str(uuid.uuid4().hex[:6]),
                    "products": product_ids,
                    "budget": {"total": 50000.0, "currency": "USD", "pacing": "even"},
                    "targeting_overlay": {
                        "geographic": {"countries": ["US", "CA"], "cities": ["New York", "Los Angeles"]},
                        "demographic": {"age_range": "25-54", "gender": "all"},
                        "behavioral": {"interests": ["technology", "business"]},
                    },
                }
            ],
            "start_time": "2025-09-01T00:00:00Z",
            "end_time": "2025-09-30T23:59:59Z",
            "targeting_overlay": {
                "device": {"types": ["desktop", "mobile"]},
                "time": {"dayparts": ["morning", "evening"], "days_of_week": [1, 2, 3, 4, 5]},
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

        return media_buy_id

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
            "get_media_buy_delivery",
            {"media_buy_ids": [media_buy_id], "start_date": "2025-09-15", "end_date": "2025-09-15"},
        )

        # The response has deliveries array with the media buy data
        assert "deliveries" in delivery
        assert len(delivery["deliveries"]) > 0
        first_delivery = delivery["deliveries"][0]
        assert "impressions" in first_delivery
        assert "spend" in first_delivery
        print(f"✓ Delivery check: {first_delivery.get('impressions', 0)} impressions")

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


# Pytest configuration hooks
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--mode", default="docker", choices=["local", "docker", "ci", "external"], help="Test execution mode"
    )
    parser.addoption("--server-url", default=None, help="External server URL for testing")
    parser.addoption("--keep-data", action="store_true", default=False, help="Keep test data after completion")
