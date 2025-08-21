"""Comprehensive integration tests for MCP endpoints.

This test file ensures all MCP tools work correctly with proper authentication
and data validation. It tests the actual server endpoints, not mocks.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from database_session import get_db_session
from models import Principal, Product, Tenant


class TestMCPEndpointsComprehensive:
    """Comprehensive tests for all MCP endpoints."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, integration_db):
        """Create test data for MCP tests."""
        from datetime import datetime

        with get_db_session() as session:
            # Create test tenant
            now = datetime.now(UTC)
            tenant = Tenant(
                tenant_id="test_mcp",
                name="Test MCP Tenant",
                subdomain="test-mcp",
                is_active=True,
                ad_server="mock",
                max_daily_budget=10000,
                enable_aee_signals=True,
                authorized_emails=[],
                authorized_domains=[],
                auto_approve_formats=["display_300x250"],
                human_review_required=False,
                admin_token="test_admin_token",
                created_at=now,
                updated_at=now,
            )
            session.add(tenant)

            # Create test principal with proper platform_mappings
            principal = Principal(
                tenant_id="test_mcp",
                principal_id="test_principal",
                name="Test Principal",
                access_token="test_mcp_token_12345",
                platform_mappings={"mock": {"id": "test_advertiser"}},
                created_at=now,
            )
            session.add(principal)

            # Create test products with all required fields
            products = [
                Product(
                    tenant_id="test_mcp",
                    product_id="display_news",
                    name="Display Ads - News Sites",
                    description="Premium display advertising on news websites",
                    formats=[
                        {
                            "format_id": "display_300x250",
                            "name": "Medium Rectangle",
                            "type": "display",
                            "width": 300,
                            "height": 250,
                        }
                    ],
                    targeting_template={"geo_country": {"values": ["US", "CA"], "required": False}},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=10.0,
                    is_custom=False,
                    countries=["US", "CA"],
                ),
                Product(
                    tenant_id="test_mcp",
                    product_id="video_sports",
                    name="Video Ads - Sports Content",
                    description="In-stream video ads on sports content",
                    formats=[
                        {
                            "format_id": "video_15s",
                            "name": "15 Second Video",
                            "type": "video",
                            "duration": 15,
                        }
                    ],
                    targeting_template={"content_category": {"values": ["sports"], "required": True}},
                    delivery_type="non_guaranteed",
                    is_fixed_price=False,
                    price_guidance={"floor": 15.0, "p50": 20.0, "p75": 25.0},
                    is_custom=False,
                    countries=["US"],
                ),
            ]
            for product in products:
                session.add(product)

            session.commit()

            # Store data for tests
            self.test_token = "test_mcp_token_12345"
            self.tenant_id = "test_mcp"
            self.principal_id = "test_principal"

    @pytest.fixture
    async def mcp_client(self, mcp_server):
        """Create MCP client with test authentication."""
        headers = {"x-adcp-auth": self.test_token}
        transport = StreamableHttpTransport(url=f"http://localhost:{mcp_server.port}/mcp/", headers=headers)
        client = Client(transport=transport)
        return client

    @pytest.mark.requires_server
    async def test_get_products_basic(self, mcp_client):
        """Test basic get_products functionality."""
        async with mcp_client as client:
            result = await client.call_tool(
                "get_products",
                {
                    "brief": "display ads for news content",
                    "promoted_offering": "Tech startup promoting AI analytics platform",
                },
            )

            assert result is not None
            content = result.structured_content if hasattr(result, "structured_content") else result
            assert "products" in content

            products = content["products"]
            assert isinstance(products, list)
            assert len(products) > 0

            # Verify product structure
            for product in products:
                assert "product_id" in product
                assert "name" in product
                assert "description" in product
                assert "formats" in product
                assert "delivery_type" in product
                assert product["delivery_type"] in ["guaranteed", "non_guaranteed"]
                assert "is_fixed_price" in product
                # Either cpm or price_guidance should be present
                assert "cpm" in product or "price_guidance" in product

    @pytest.mark.requires_server
    async def test_get_products_filtering(self, mcp_client):
        """Test that get_products filters based on brief."""
        async with mcp_client as client:
            # Search for news content
            result = await client.call_tool(
                "get_products",
                {
                    "brief": "display advertising on news websites",
                    "promoted_offering": "B2B software company",
                },
            )

            content = result.structured_content if hasattr(result, "structured_content") else result
            products = content["products"]

            # Should find display_news product
            news_products = [p for p in products if "news" in p["name"].lower()]
            assert len(news_products) > 0

    @pytest.mark.requires_server
    async def test_get_products_missing_required_field(self, mcp_client):
        """Test that get_products fails without promoted_offering."""
        async with mcp_client as client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "get_products",
                    {"brief": "display ads"},  # Missing promoted_offering
                )

            # Should fail with validation error
            assert "promoted_offering" in str(exc_info.value).lower()

    @pytest.mark.requires_server
    async def test_create_media_buy(self, mcp_client):
        """Test creating a media buy."""
        async with mcp_client as client:
            # First get products
            products_result = await client.call_tool(
                "get_products",
                {
                    "brief": "news advertising",
                    "promoted_offering": "Tech company",
                },
            )

            products_content = (
                products_result.structured_content
                if hasattr(products_result, "structured_content")
                else products_result
            )
            products = products_content["products"]
            assert len(products) > 0

            # Create media buy with first product
            product_id = products[0]["product_id"]

            start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

            result = await client.call_tool(
                "create_media_buy",
                {
                    "product_ids": [product_id],
                    "total_budget": 5000.0,
                    "flight_start_date": start_date,
                    "flight_end_date": end_date,
                    "targeting_overlay": {
                        "geo_country_any_of": ["US"],
                    },
                },
            )

            content = result.structured_content if hasattr(result, "structured_content") else result
            assert "media_buy_id" in content
            assert "status" in content
            assert content["status"] in ["pending", "active", "draft"]

    @pytest.mark.requires_server
    async def test_invalid_auth(self):
        """Test that invalid authentication is rejected."""
        headers = {"x-adcp-auth": "invalid_token"}
        transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
        client = Client(transport=transport)

        async with client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "get_products",
                    {
                        "brief": "test",
                        "promoted_offering": "test",
                    },
                )

            # Should get authentication error
            assert "auth" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    @pytest.mark.requires_server
    async def test_get_signals_optional(self, mcp_client):
        """Test the optional get_signals endpoint."""
        async with mcp_client as client:
            # get_signals is optional, so it might not exist
            try:
                result = await client.call_tool(
                    "get_signals",
                    {
                        "query": "sports",
                        "type": "contextual",
                    },
                )

                content = result.structured_content if hasattr(result, "structured_content") else result
                assert "signals" in content
                assert isinstance(content["signals"], list)
            except Exception as e:
                # If tool doesn't exist, that's ok (it's optional)
                if "unknown tool" not in str(e).lower():
                    raise

    @pytest.mark.requires_server
    async def test_full_workflow(self, mcp_client):
        """Test a complete workflow from discovery to media buy."""
        async with mcp_client as client:
            # 1. Discover products
            products_result = await client.call_tool(
                "get_products",
                {
                    "brief": "Looking for premium display advertising",
                    "promoted_offering": "Enterprise SaaS platform for data analytics",
                },
            )

            products_content = (
                products_result.structured_content
                if hasattr(products_result, "structured_content")
                else products_result
            )
            assert len(products_content["products"]) > 0

            # 2. Create media buy
            product = products_content["products"][0]
            start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=37)).strftime("%Y-%m-%d")

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "product_ids": [product["product_id"]],
                    "total_budget": 10000.0,
                    "flight_start_date": start_date,
                    "flight_end_date": end_date,
                },
            )

            buy_content = buy_result.structured_content if hasattr(buy_result, "structured_content") else buy_result
            assert "media_buy_id" in buy_content
            media_buy_id = buy_content["media_buy_id"]

            # 3. Get media buy status
            status_result = await client.call_tool(
                "get_media_buy_status",
                {"media_buy_id": media_buy_id},
            )

            status_content = (
                status_result.structured_content if hasattr(status_result, "structured_content") else status_result
            )
            assert status_content["media_buy_id"] == media_buy_id
            assert "status" in status_content
            assert "packages" in status_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
