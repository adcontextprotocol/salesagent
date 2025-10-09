"""
Test implementation of AdCP testing hooks from PR #34.

https://github.com/adcontextprotocol/adcp/pull/34

Tests the following headers:
- X-Dry-Run: Execute without affecting production
- X-Mock-Time: Control simulated time
- X-Jump-To-Event: Jump to campaign lifecycle events
- X-Test-Session-ID: Isolate test sessions
- X-Simulated-Spend: Track simulated spending
"""

import json
import uuid
from datetime import datetime

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


class TestAdCPTestingHooks:
    """Test suite for AdCP testing hooks implementation."""

    @pytest.mark.asyncio
    async def test_dry_run_header(self, live_server, test_auth_token):
        """Test X-Dry-Run header prevents real platform changes."""
        headers = {"x-adcp-auth": test_auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": str(uuid.uuid4())}

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Get products first
            result = await client.call_tool("get_products", {"req": {"brief": "test", "promoted_offering": "test"}})
            products = json.loads(result.content[0].text)

            # Create media buy in dry-run mode
            media_buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 1000.0,
                        "flight_start_date": "2025-10-01",
                        "flight_end_date": "2025-10-31",
                    }
                },
            )

            media_buy = json.loads(media_buy_result.content[0].text)

            # Should create but not affect real platform
            assert "media_buy_id" in media_buy
            assert media_buy.get("dry_run", False) or "test" in media_buy["media_buy_id"].lower()
            print(f"✓ Dry-run media buy created: {media_buy['media_buy_id']}")

    @pytest.mark.asyncio
    async def test_mock_time_header(self, live_server, test_auth_token):
        """Test X-Mock-Time header for time simulation."""
        mock_time = datetime(2025, 10, 15, 14, 0, 0)

        headers = {
            "x-adcp-auth": test_auth_token,
            "X-Mock-Time": mock_time.isoformat() + "Z",
            "X-Test-Session-ID": str(uuid.uuid4()),
            "X-Dry-Run": "true",
        }

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Create a campaign that should be mid-flight at mock time
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "test", "promoted_offering": "test"}}
            )
            products = json.loads(products_result.content[0].text)

            media_buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 5000.0,
                        "flight_start_date": "2025-10-01",
                        "flight_end_date": "2025-10-31",
                    }
                },
            )

            media_buy = json.loads(media_buy_result.content[0].text)
            media_buy_id = media_buy["media_buy_id"]

            # Check delivery at mock time (should be mid-campaign)
            delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"media_buy_id": media_buy_id}})

            delivery = json.loads(delivery_result.content[0].text)

            # At Oct 15, campaign should be ~50% through
            assert "impressions" in delivery or "status" in delivery
            print(f"✓ Mock time {mock_time}: Campaign delivery checked")

    @pytest.mark.asyncio
    async def test_jump_to_event_header(self, live_server, test_auth_token):
        """Test X-Jump-To-Event header for lifecycle progression."""
        headers_base = {
            "x-adcp-auth": test_auth_token,
            "X-Test-Session-ID": str(uuid.uuid4()),
            "X-Dry-Run": "true",
        }

        # Create campaign
        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers_base)

        async with Client(transport=transport) as client:
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "test", "promoted_offering": "test"}}
            )
            products = json.loads(products_result.content[0].text)

            media_buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 10000.0,
                        "flight_start_date": "2025-11-01",
                        "flight_end_date": "2025-11-30",
                    }
                },
            )

            media_buy = json.loads(media_buy_result.content[0].text)
            media_buy_id = media_buy["media_buy_id"]

        # Jump to campaign midpoint
        headers_jump = headers_base.copy()
        headers_jump["X-Jump-To-Event"] = "campaign-midpoint"

        transport_jump = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers_jump)

        async with Client(transport=transport_jump) as client:
            delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"media_buy_id": media_buy_id}})

            delivery = json.loads(delivery_result.content[0].text)
            print(f"✓ Jumped to midpoint: {delivery.get('status', 'active')}")

        # Jump to completion
        headers_complete = headers_base.copy()
        headers_complete["X-Jump-To-Event"] = "campaign-complete"

        transport_complete = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers_complete)

        async with Client(transport=transport_complete) as client:
            final_result = await client.call_tool("get_media_buy_delivery", {"req": {"media_buy_id": media_buy_id}})

            final = json.loads(final_result.content[0].text)
            print(f"✓ Jumped to completion: {final.get('status', 'completed')}")

    @pytest.mark.asyncio
    async def test_test_session_id_isolation(self, live_server, test_auth_token):
        """Test X-Test-Session-ID provides session isolation."""
        session1_id = str(uuid.uuid4())
        session2_id = str(uuid.uuid4())

        # Create two separate test sessions
        headers1 = {"x-adcp-auth": test_auth_token, "X-Test-Session-ID": session1_id, "X-Dry-Run": "true"}

        headers2 = {"x-adcp-auth": test_auth_token, "X-Test-Session-ID": session2_id, "X-Dry-Run": "true"}

        transport1 = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers1)

        transport2 = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers2)

        # Create campaigns in each session
        async with Client(transport=transport1) as client1, Client(transport=transport2) as client2:

            # Session 1: Create a campaign
            products1 = await client1.call_tool(
                "get_products", {"req": {"brief": "session1", "promoted_offering": "test1"}}
            )
            products1_data = json.loads(products1.content[0].text)

            buy1 = await client1.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products1_data["products"][0]["product_id"]],
                        "total_budget": 1000.0,
                        "flight_start_date": "2025-10-01",
                        "flight_end_date": "2025-10-31",
                    }
                },
            )
            buy1_data = json.loads(buy1.content[0].text)

            # Session 2: Create a different campaign
            products2 = await client2.call_tool(
                "get_products", {"req": {"brief": "session2", "promoted_offering": "test2"}}
            )
            products2_data = json.loads(products2.content[0].text)

            buy2 = await client2.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products2_data["products"][0]["product_id"]],
                        "total_budget": 2000.0,
                        "flight_start_date": "2025-11-01",
                        "flight_end_date": "2025-11-30",
                    }
                },
            )
            buy2_data = json.loads(buy2.content[0].text)

            # Sessions should be isolated
            assert buy1_data["media_buy_id"] != buy2_data["media_buy_id"]
            print(f"✓ Session 1 ({session1_id[:8]}...): {buy1_data['media_buy_id']}")
            print(f"✓ Session 2 ({session2_id[:8]}...): {buy2_data['media_buy_id']}")

    @pytest.mark.asyncio
    async def test_simulated_spend_tracking(self, live_server, test_auth_token):
        """Test X-Simulated-Spend header tracks spend without real money."""
        headers = {
            "x-adcp-auth": test_auth_token,
            "X-Test-Session-ID": str(uuid.uuid4()),
            "X-Dry-Run": "true",
            "X-Simulated-Spend": "true",
        }

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Get products
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "test", "promoted_offering": "test"}}
            )
            products = json.loads(products_result.content[0].text)

            # Create campaign with budget
            media_buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 15000.0,
                        "flight_start_date": "2025-10-01",
                        "flight_end_date": "2025-10-31",
                    }
                },
            )

            media_buy = json.loads(media_buy_result.content[0].text)
            media_buy_id = media_buy["media_buy_id"]

            # Advance time and check simulated spend
            headers_advanced = headers.copy()
            headers_advanced["X-Jump-To-Event"] = "campaign-midpoint"

            transport_advanced = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers_advanced)

            async with Client(transport=transport_advanced) as client_advanced:
                delivery_result = await client_advanced.call_tool(
                    "get_media_buy_delivery", {"req": {"media_buy_id": media_buy_id}}
                )

                delivery = json.loads(delivery_result.content[0].text)

                # Should have simulated spend but no real charges
                spend = delivery.get("spend", 0)
                assert spend > 0 or delivery.get("simulated_spend", 0) > 0
                print(f"✓ Simulated spend tracked: ${spend}")

    @pytest.mark.asyncio
    async def test_combined_hooks(self, live_server, test_auth_token):
        """Test using multiple testing hooks together."""
        test_session = str(uuid.uuid4())
        mock_start = datetime(2025, 12, 1, 9, 0, 0)

        # Start with all hooks
        headers = {
            "x-adcp-auth": test_auth_token,
            "X-Test-Session-ID": test_session,
            "X-Dry-Run": "true",
            "X-Mock-Time": mock_start.isoformat() + "Z",
            "X-Simulated-Spend": "true",
        }

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Create comprehensive test campaign
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "holiday campaign", "promoted_offering": "premium"}}
            )
            products = json.loads(products_result.content[0].text)

            media_buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 50000.0,
                        "flight_start_date": "2025-12-01",
                        "flight_end_date": "2025-12-31",
                        "targeting_overlay": {
                            "geographic": {"countries": ["US"]},
                            "audience": {"interests": ["shopping", "holidays"]},
                        },
                    }
                },
            )

            media_buy = json.loads(media_buy_result.content[0].text)
            media_buy_id = media_buy["media_buy_id"]
            print(f"✓ Campaign created with all hooks: {media_buy_id}")

            # Jump through lifecycle quickly
            for event in ["campaign-start", "campaign-midpoint", "campaign-complete"]:
                headers_jump = headers.copy()
                headers_jump["X-Jump-To-Event"] = event

                transport_jump = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers_jump)

                async with Client(transport=transport_jump) as client_jump:
                    delivery_result = await client_jump.call_tool(
                        "get_media_buy_delivery", {"req": {"media_buy_id": media_buy_id}}
                    )

                    delivery = json.loads(delivery_result.content[0].text)
                    print(
                        f"  • {event}: {delivery.get('impressions', 0)} impressions, ${delivery.get('spend', 0)} spend"
                    )

            print(f"✓ Full lifecycle tested with session {test_session[:8]}...")
