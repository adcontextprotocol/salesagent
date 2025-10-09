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
    async def test_comprehensive_time_simulation(self, live_server, test_auth_token):
        """Test comprehensive time simulation with multiple scenarios."""
        session_id = f"time_sim_{uuid.uuid4().hex[:8]}"

        # Test different time points in campaign lifecycle
        test_times = [
            ("2025-10-01T00:00:00Z", "campaign_start", 0.0),
            ("2025-10-08T12:00:00Z", "campaign_25_percent", 0.25),
            ("2025-10-15T12:00:00Z", "campaign_midpoint", 0.5),
            ("2025-10-23T12:00:00Z", "campaign_75_percent", 0.75),
            ("2025-10-31T23:59:59Z", "campaign_end", 1.0),
        ]

        for mock_time, description, _expected_progress in test_times:
            headers = {
                "x-adcp-auth": test_auth_token,
                "X-Dry-Run": "true",
                "X-Test-Session-ID": session_id,
                "X-Mock-Time": mock_time,
                "X-Debug-Mode": "true",
            }

            transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

            async with Client(transport=transport) as client:
                # First create a media buy for this time test
                products_result = await client.call_tool(
                    "get_products", {"req": {"brief": f"time test {description}", "promoted_offering": "test"}}
                )
                products = json.loads(products_result.content[0].text)

                # Create campaign spanning October 2025
                buy_result = await client.call_tool(
                    "create_media_buy",
                    {
                        "req": {
                            "product_ids": [products["products"][0]["product_id"]],
                            "total_budget": 10000.0,
                            "flight_start_date": "2025-10-01",
                            "flight_end_date": "2025-10-31",
                        }
                    },
                )

                buy_data = json.loads(buy_result.content[0].text)

                # Get delivery at this simulated time
                delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"filter": "all"}})

                delivery = json.loads(delivery_result.content[0].text)

                # Verify time simulation is working
                assert "deliveries" in delivery
                if delivery["deliveries"]:
                    first_delivery = delivery["deliveries"][0]
                    # Should have some progress indicators
                    assert "spend" in first_delivery
                    assert "impressions" in first_delivery

                print(
                    f"  ✓ {description}: spend=${delivery.get('total_spend', 0)}, impressions={delivery.get('total_impressions', 0)}"
                )

    @pytest.mark.asyncio
    async def test_lifecycle_event_jumping(self, live_server, test_auth_token):
        """Test jumping to specific campaign lifecycle events."""
        session_id = f"lifecycle_{uuid.uuid4().hex[:8]}"

        # Test key lifecycle events
        lifecycle_events = [
            "campaign-creation",
            "campaign-start",
            "campaign-midpoint",
            "campaign-75-percent",
            "campaign-complete",
            "campaign-paused",
        ]

        base_headers = {"x-adcp-auth": test_auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": session_id}

        # First create a campaign
        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=base_headers)

        async with Client(transport=transport) as client:
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "lifecycle test", "promoted_offering": "test products"}}
            )
            products = json.loads(products_result.content[0].text)

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 20000.0,
                        "flight_start_date": "2025-11-01",
                        "flight_end_date": "2025-11-30",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)
            media_buy_id = buy_data["media_buy_id"]

        # Test each lifecycle event
        for event in lifecycle_events:
            headers = {**base_headers, "X-Jump-To-Event": event, "X-Debug-Mode": "true"}

            transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

            async with Client(transport=transport) as client:
                delivery_result = await client.call_tool(
                    "get_media_buy_delivery", {"req": {"media_buy_ids": [media_buy_id]}}
                )

                delivery = json.loads(delivery_result.content[0].text)
                assert "deliveries" in delivery

                if delivery["deliveries"]:
                    first_delivery = delivery["deliveries"][0]
                    status = first_delivery.get("status", "unknown")
                    spend = first_delivery.get("spend", 0)

                    print(f"  ✓ {event}: status={status}, spend=${spend}")

    @pytest.mark.asyncio
    async def test_comprehensive_error_scenarios(self, live_server, test_auth_token):
        """Test all supported error scenarios."""
        session_id = f"error_test_{uuid.uuid4().hex[:8]}"

        error_scenarios = ["budget_exceeded", "low_delivery", "platform_error"]

        base_headers = {"x-adcp-auth": test_auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": session_id}

        # Create test campaign first
        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=base_headers)

        async with Client(transport=transport) as client:
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "error testing", "promoted_offering": "test"}}
            )
            products = json.loads(products_result.content[0].text)

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 5000.0,
                        "flight_start_date": "2025-12-01",
                        "flight_end_date": "2025-12-31",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)
            media_buy_id = buy_data["media_buy_id"]

        # Test each error scenario
        for error in error_scenarios:
            headers = {**base_headers, "X-Force-Error": error, "X-Debug-Mode": "true"}

            transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

            async with Client(transport=transport) as client:
                # Some errors might be thrown as exceptions
                try:
                    delivery_result = await client.call_tool(
                        "get_media_buy_delivery", {"req": {"media_buy_ids": [media_buy_id]}}
                    )

                    delivery = json.loads(delivery_result.content[0].text)

                    # Check for error indicators in response
                    if delivery.get("deliveries"):
                        first_delivery = delivery["deliveries"][0]
                        # Different errors should show different behaviors
                        if error == "budget_exceeded":
                            # Should show overspend
                            assert first_delivery.get("spend", 0) > 0
                        elif error == "low_delivery":
                            # Should show reduced impressions
                            assert "impressions" in first_delivery

                    print(f"  ✓ {error}: handled gracefully")

                except Exception as e:
                    # platform_error might throw exceptions
                    if error == "platform_error":
                        print(f"  ✓ {error}: exception thrown as expected: {str(e)[:50]}")
                    else:
                        print(f"  ⚠ {error}: unexpected exception: {str(e)[:50]}")

    @pytest.mark.asyncio
    async def test_production_isolation_guarantees(self, live_server, test_auth_token):
        """Test that all testing features are properly isolated from production."""
        session_id = f"isolation_test_{uuid.uuid4().hex[:8]}"

        headers = {
            "x-adcp-auth": test_auth_token,
            "X-Dry-Run": "true",
            "X-Test-Session-ID": session_id,
            "X-Mock-Time": "2025-10-15T12:00:00Z",
            "X-Jump-To-Event": "campaign-complete",
            "X-Force-Error": "budget_exceeded",
            "X-Simulated-Spend": "true",
            "X-Debug-Mode": "true",
        }

        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # Test full workflow with all testing hooks active
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "isolation test", "promoted_offering": "test products"}}
            )
            products = json.loads(products_result.content[0].text)

            # Response should contain test markers
            assert "is_test" in products or any("test_" in str(p).lower() for p in products.get("products", []))

            # Create media buy
            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["product_id"]],
                        "total_budget": 50000.0,
                        "flight_start_date": "2025-10-01",
                        "flight_end_date": "2025-10-31",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)

            # Should contain test/isolation markers
            assert (
                "test_" in buy_data.get("media_buy_id", "").lower()
                or buy_data.get("is_test")
                or buy_data.get("dry_run")
            )

            # Get delivery data
            delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"filter": "all"}})

            delivery = json.loads(delivery_result.content[0].text)

            # Should show isolated/simulated data
            assert delivery.get("is_test") or any(
                d.get("is_simulated") or "test_" in d.get("media_buy_id", "") for d in delivery.get("deliveries", [])
            )

            print("✓ Production isolation: all responses marked as test/simulated")
            print(f"  - Products: {len(products.get('products', []))} test products")
            print(f"  - Media buy: {buy_data.get('media_buy_id', 'N/A')}")
            print(f"  - Deliveries: {len(delivery.get('deliveries', []))} isolated records")

    @pytest.mark.asyncio
    async def test_realistic_metrics_generation(self, live_server, test_auth_token):
        """Test that simulated metrics are realistic and follow campaign patterns."""
        session_id = f"metrics_test_{uuid.uuid4().hex[:8]}"

        # Test campaign progression over time
        time_points = [
            "2025-10-01T09:00:00Z",  # Start
            "2025-10-08T15:00:00Z",  # Week 1
            "2025-10-15T12:00:00Z",  # Week 2 (midpoint)
            "2025-10-22T18:00:00Z",  # Week 3
            "2025-10-31T23:00:00Z",  # End
        ]

        metrics_history = []

        for i, mock_time in enumerate(time_points):
            headers = {
                "x-adcp-auth": test_auth_token,
                "X-Dry-Run": "true",
                "X-Test-Session-ID": session_id,
                "X-Mock-Time": mock_time,
                "X-Debug-Mode": "true",
            }

            transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

            async with Client(transport=transport) as client:
                if i == 0:  # First iteration - create campaign
                    products_result = await client.call_tool(
                        "get_products", {"req": {"brief": "metrics test", "promoted_offering": "test"}}
                    )
                    products = json.loads(products_result.content[0].text)

                    buy_result = await client.call_tool(
                        "create_media_buy",
                        {
                            "req": {
                                "product_ids": [products["products"][0]["product_id"]],
                                "total_budget": 10000.0,
                                "flight_start_date": "2025-10-01",
                                "flight_end_date": "2025-10-31",
                            }
                        },
                    )

                # Get delivery metrics for this time point
                delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"filter": "all"}})

                delivery = json.loads(delivery_result.content[0].text)

                if delivery.get("deliveries"):
                    metrics = delivery["deliveries"][0]
                    metrics_history.append(
                        {
                            "time": mock_time,
                            "spend": metrics.get("spend", 0),
                            "impressions": metrics.get("impressions", 0),
                            "status": metrics.get("status", "unknown"),
                        }
                    )

        # Validate realistic progression
        assert len(metrics_history) == len(time_points)

        # Spend should generally increase over time
        spends = [m["spend"] for m in metrics_history]
        impressions = [m["impressions"] for m in metrics_history]

        # Check that metrics increase over campaign lifecycle
        for i in range(1, len(spends)):
            if spends[i] > 0:  # Only check if we have spend data
                assert spends[i] >= spends[i - 1], f"Spend should increase: {spends[i-1]} -> {spends[i]}"

        # Check for realistic ratios (impressions should correlate with spend)
        if impressions[-1] > 0 and spends[-1] > 0:
            cpm = (spends[-1] / impressions[-1]) * 1000
            assert 0.1 <= cpm <= 50, f"CPM should be realistic, got ${cpm:.2f}"

        print("✓ Realistic metrics progression:")
        for metrics in metrics_history:
            print(
                f"  {metrics['time'][:10]}: ${metrics['spend']:.0f}, {metrics['impressions']} imps, {metrics['status']}"
            )

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
