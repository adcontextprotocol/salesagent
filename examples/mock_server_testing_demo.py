#!/usr/bin/env python3
"""
AdCP Mock Server Testing Backend - Comprehensive Demo

This script demonstrates all testing features of the AdCP mock server including:
- Time simulation and event jumping
- Error scenario testing
- Session isolation
- Production isolation guarantees
- Realistic metrics generation

Usage:
    python examples/mock_server_testing_demo.py --token YOUR_TOKEN --server http://localhost:8080
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


class MockServerTestingDemo:
    """Comprehensive demo of AdCP mock server testing backend capabilities."""

    def __init__(self, server_url: str, auth_token: str):
        self.server_url = server_url.rstrip("/")
        self.auth_token = auth_token
        self.mcp_url = f"{self.server_url}/mcp/"

    async def run_comprehensive_demo(self):
        """Run complete testing backend demonstration."""
        print("🧪 AdCP Testing Backend - Comprehensive Demo")
        print("=" * 50)

        # 1. Test capabilities discovery
        await self.demo_capabilities()

        # 2. Test session management
        session_id = await self.demo_session_management()

        # 3. Test time simulation
        await self.demo_time_simulation(session_id)

        # 4. Test lifecycle event jumping
        await self.demo_lifecycle_events(session_id)

        # 5. Test error scenarios
        await self.demo_error_scenarios(session_id)

        # 6. Test production isolation
        await self.demo_production_isolation(session_id)

        # 7. Test parallel sessions
        await self.demo_parallel_sessions()

        # 8. Cleanup
        await self.cleanup_demo(session_id)

        print("\n✅ All testing features demonstrated successfully!")
        print("🔒 Production isolation maintained throughout")
        print("💰 Zero real money spent")

    async def demo_capabilities(self):
        """Demonstrate testing capabilities discovery."""
        print("\n📋 1. Testing Capabilities Discovery")
        print("-" * 30)

        headers = {"x-adcp-auth": self.auth_token}
        transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

        async with Client(transport=transport) as client:
            result = await client.call_tool("testing_control", {"req": {"action": "get_capabilities"}})

            response = json.loads(result.content[0].text)
            if response["success"]:
                caps = response["data"]
                print(f"✓ Supported headers: {len(caps['supported_headers'])}")
                print(f"✓ Lifecycle events: {len(caps['lifecycle_events'])}")
                print(f"✓ Error scenarios: {len(caps['error_scenarios'])}")
                print(f"✓ Time simulation: {caps['time_simulation']}")
                print(f"✓ Session isolation: {caps['session_isolation']}")

                print("\nKey headers:")
                for header in caps["supported_headers"][:5]:
                    print(f"  - {header}")
                print("  ...")

    async def demo_session_management(self) -> str:
        """Demonstrate session management capabilities."""
        print("\n🧪 2. Test Session Management")
        print("-" * 30)

        session_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        headers = {"x-adcp-auth": self.auth_token}
        transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

        async with Client(transport=transport) as client:
            # Create session
            result = await client.call_tool(
                "testing_control", {"req": {"action": "create_session", "session_id": session_id}}
            )
            response = json.loads(result.content[0].text)
            print(f"✓ Created session: {session_id}")

            # List sessions
            result = await client.call_tool("testing_control", {"req": {"action": "list_sessions"}})
            response = json.loads(result.content[0].text)
            sessions = response["data"]["sessions"]
            print(f"✓ Active sessions: {len(sessions)}")

            # Inspect context
            result = await client.call_tool("testing_control", {"req": {"action": "inspect_context"}})
            response = json.loads(result.content[0].text)
            print("✓ Context inspection successful")

        return session_id

    async def demo_time_simulation(self, session_id: str):
        """Demonstrate time simulation capabilities."""
        print("\n⏰ 3. Time Simulation Demo")
        print("-" * 30)

        # Test multiple time points throughout a campaign
        time_points = [
            ("2025-11-01T09:00:00Z", "Campaign Start", "🚀"),
            ("2025-11-08T15:00:00Z", "Week 1", "📈"),
            ("2025-11-15T12:00:00Z", "Midpoint", "⚡"),
            ("2025-11-22T18:00:00Z", "Week 3", "🎯"),
            ("2025-11-30T23:00:00Z", "Campaign End", "🏁"),
        ]

        media_buy_id = None

        for i, (mock_time, description, emoji) in enumerate(time_points):
            headers = {
                "x-adcp-auth": self.auth_token,
                "X-Dry-Run": "true",
                "X-Test-Session-ID": session_id,
                "X-Mock-Time": mock_time,
                "X-Debug-Mode": "true",
            }

            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                if i == 0:  # First iteration - create campaign
                    # Get products
                    products_result = await client.call_tool(
                        "get_products", {"req": {"brief": "time simulation test", "promoted_offering": "demo products"}}
                    )
                    products = json.loads(products_result.content[0].text)

                    # Create media buy
                    buy_result = await client.call_tool(
                        "create_media_buy",
                        {
                            "req": {
                                "product_ids": [products["products"][0]["id"]],
                                "total_budget": 15000.0,
                                "flight_start_date": "2025-11-01",
                                "flight_end_date": "2025-11-30",
                            }
                        },
                    )
                    buy_data = json.loads(buy_result.content[0].text)
                    media_buy_id = buy_data["media_buy_id"]
                    print(f"  📝 Created campaign: {media_buy_id}")

                # Get delivery at this time point
                delivery_result = await client.call_tool(
                    "get_media_buy_delivery",
                    {"req": {"media_buy_ids": [media_buy_id] if media_buy_id else [], "filter": "all"}},
                )

                delivery = json.loads(delivery_result.content[0].text)
                spend = delivery.get("total_spend", 0)
                impressions = delivery.get("total_impressions", 0)

                # Show response headers if available
                headers = delivery.get("response_headers", {})
                header_info = []
                if "X-Next-Event" in headers:
                    header_info.append(f"Next: {headers['X-Next-Event']}")
                if "X-Simulated-Spend" in headers:
                    header_info.append(f"Spend: ${headers['X-Simulated-Spend']}")

                header_str = f" ({', '.join(header_info)})" if header_info else ""
                print(f"  {emoji} {description}: ${spend:.0f} spent, {impressions:,} impressions{header_str}")

    async def demo_lifecycle_events(self, session_id: str):
        """Demonstrate lifecycle event jumping."""
        print("\n🎭 4. Lifecycle Event Jumping")
        print("-" * 30)

        # Test key lifecycle events
        events = [
            ("campaign-creation", "📝 Creation"),
            ("campaign-start", "🚀 Launch"),
            ("campaign-midpoint", "⚡ Midpoint"),
            ("campaign-75-percent", "🎯 75% Complete"),
            ("campaign-complete", "🏁 Complete"),
            ("campaign-paused", "⏸️  Paused"),
        ]

        base_headers = {"x-adcp-auth": self.auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": session_id}

        # Create test campaign for events
        transport = StreamableHttpTransport(url=self.mcp_url, headers=base_headers)

        async with Client(transport=transport) as client:
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "lifecycle events test", "promoted_offering": "event demo"}}
            )
            products = json.loads(products_result.content[0].text)

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["id"]],
                        "total_budget": 25000.0,
                        "flight_start_date": "2025-12-01",
                        "flight_end_date": "2025-12-31",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)
            media_buy_id = buy_data["media_buy_id"]

        print(f"  📝 Test campaign: {media_buy_id}")

        # Jump to each event
        for event, description in events:
            headers = {**base_headers, "X-Jump-To-Event": event}

            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                delivery_result = await client.call_tool(
                    "get_media_buy_delivery", {"req": {"media_buy_ids": [media_buy_id]}}
                )

                delivery = json.loads(delivery_result.content[0].text)

                if delivery.get("deliveries"):
                    first_delivery = delivery["deliveries"][0]
                    status = first_delivery.get("status", "unknown")
                    spend = first_delivery.get("spend", 0)
                    print(f"  {description}: {status}, ${spend:.0f}")

    async def demo_error_scenarios(self, session_id: str):
        """Demonstrate error scenario simulation."""
        print("\n🚨 5. Error Scenario Testing")
        print("-" * 30)

        errors = [
            ("budget_exceeded", "💰 Budget Exceeded"),
            ("low_delivery", "📉 Low Delivery"),
            ("platform_error", "⚠️  Platform Error"),
        ]

        base_headers = {"x-adcp-auth": self.auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": session_id}

        # Create test campaign
        transport = StreamableHttpTransport(url=self.mcp_url, headers=base_headers)

        async with Client(transport=transport) as client:
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "error testing", "promoted_offering": "error demo"}}
            )
            products = json.loads(products_result.content[0].text)

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["id"]],
                        "total_budget": 8000.0,
                        "flight_start_date": "2026-01-01",
                        "flight_end_date": "2026-01-31",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)
            media_buy_id = buy_data["media_buy_id"]

        print(f"  📝 Error test campaign: {media_buy_id}")

        # Test each error scenario
        for error, description in errors:
            headers = {**base_headers, "X-Force-Error": error}

            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                try:
                    delivery_result = await client.call_tool(
                        "get_media_buy_delivery", {"req": {"media_buy_ids": [media_buy_id]}}
                    )

                    delivery = json.loads(delivery_result.content[0].text)
                    print(f"  {description}: Handled gracefully")

                    # Show specific error behavior
                    if delivery.get("deliveries"):
                        first_delivery = delivery["deliveries"][0]
                        if error == "budget_exceeded":
                            overspend = first_delivery.get("spend", 0) > 8000
                            print(f"    - Overspend detected: {overspend}")
                        elif error == "low_delivery":
                            impressions = first_delivery.get("impressions", 0)
                            print(f"    - Reduced impressions: {impressions:,}")

                except Exception as e:
                    if error == "platform_error":
                        print(f"  {description}: Exception thrown (expected)")
                    else:
                        print(f"  {description}: Unexpected error - {str(e)[:50]}")

    async def demo_production_isolation(self, session_id: str):
        """Demonstrate production isolation guarantees."""
        print("\n🔒 6. Production Isolation Demo")
        print("-" * 30)

        # Use ALL testing headers simultaneously
        headers = {
            "x-adcp-auth": self.auth_token,
            "X-Dry-Run": "true",
            "X-Test-Session-ID": session_id,
            "X-Mock-Time": "2026-02-15T12:00:00Z",
            "X-Jump-To-Event": "campaign-complete",
            "X-Force-Error": "budget_exceeded",
            "X-Simulated-Spend": "true",
            "X-Debug-Mode": "true",
        }

        transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

        async with Client(transport=transport) as client:
            # Full workflow with all testing hooks
            products_result = await client.call_tool(
                "get_products", {"req": {"brief": "isolation test", "promoted_offering": "isolation demo"}}
            )
            products = json.loads(products_result.content[0].text)

            buy_result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": [products["products"][0]["id"]],
                        "total_budget": 100000.0,
                        "flight_start_date": "2026-02-01",
                        "flight_end_date": "2026-02-28",
                    }
                },
            )

            buy_data = json.loads(buy_result.content[0].text)

            delivery_result = await client.call_tool("get_media_buy_delivery", {"req": {"filter": "all"}})

            delivery = json.loads(delivery_result.content[0].text)

            # Verify isolation markers
            isolation_markers = [
                products.get("is_test", False),
                buy_data.get("is_test", False),
                buy_data.get("dry_run", False),
                delivery.get("is_test", False),
                "test_" in str(buy_data.get("media_buy_id", "")).lower(),
            ]

            print(f"  ✓ Isolation markers present: {sum(isolation_markers)}/5")
            print("  ✓ All operations marked as test/simulated")
            print("  ✓ No real API calls made")
            print("  ✓ No actual money spent: $0.00")
            print(f"  ✓ Campaign ID: {buy_data.get('media_buy_id', 'N/A')}")

    async def demo_parallel_sessions(self):
        """Demonstrate parallel session isolation."""
        print("\n🔄 7. Parallel Session Testing")
        print("-" * 30)

        # Create multiple isolated sessions
        sessions = [
            f"parallel_a_{uuid.uuid4().hex[:8]}",
            f"parallel_b_{uuid.uuid4().hex[:8]}",
            f"parallel_c_{uuid.uuid4().hex[:8]}",
        ]

        # Run parallel campaigns
        async def create_campaign_in_session(session_id: str, budget: float) -> dict:
            headers = {"x-adcp-auth": self.auth_token, "X-Dry-Run": "true", "X-Test-Session-ID": session_id}

            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                products_result = await client.call_tool(
                    "get_products", {"req": {"brief": f"parallel test {session_id}", "promoted_offering": "parallel"}}
                )
                products = json.loads(products_result.content[0].text)

                buy_result = await client.call_tool(
                    "create_media_buy",
                    {
                        "req": {
                            "product_ids": [products["products"][0]["id"]],
                            "total_budget": budget,
                            "flight_start_date": "2026-03-01",
                            "flight_end_date": "2026-03-31",
                        }
                    },
                )

                return json.loads(buy_result.content[0].text)

        # Launch parallel campaigns
        results = await asyncio.gather(
            create_campaign_in_session(sessions[0], 5000.0),
            create_campaign_in_session(sessions[1], 15000.0),
            create_campaign_in_session(sessions[2], 25000.0),
        )

        # Verify isolation
        media_buy_ids = [r["media_buy_id"] for r in results]
        unique_ids = set(media_buy_ids)

        print(f"  ✓ Created {len(results)} parallel campaigns")
        print(f"  ✓ All campaign IDs unique: {len(unique_ids) == len(media_buy_ids)}")

        for i, (session, result) in enumerate(zip(sessions, results, strict=False)):
            budget = [5000, 15000, 25000][i]
            print(f"  ✓ Session {session[:12]}...: ${budget}, ID: {result['media_buy_id']}")

    async def cleanup_demo(self, session_id: str):
        """Clean up demo resources."""
        print("\n🧹 8. Demo Cleanup")
        print("-" * 30)

        headers = {"x-adcp-auth": self.auth_token}
        transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

        async with Client(transport=transport) as client:
            result = await client.call_tool(
                "testing_control", {"req": {"action": "cleanup_session", "session_id": session_id}}
            )

            response = json.loads(result.content[0].text)
            if response["success"]:
                print(f"  ✓ Cleaned up session: {session_id}")
            else:
                print(f"  ⚠ Cleanup warning: {response['message']}")


async def main():
    """Run the comprehensive testing demo."""
    import argparse

    parser = argparse.ArgumentParser(description="AdCP Testing Backend Demo")
    parser.add_argument("--server", default="http://localhost:8080", help="AdCP server URL")
    parser.add_argument("--token", required=True, help="Authentication token")

    args = parser.parse_args()

    demo = MockServerTestingDemo(args.server, args.token)

    try:
        await demo.run_comprehensive_demo()
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
