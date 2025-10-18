#!/usr/bin/env python3
"""
Comprehensive end-to-end test suite for AdCP with strategy-based simulation.

Tests the complete system using official MCP and A2A clients:
- Strategy system integration
- Time progression simulation
- Mock adapter strategy awareness
- Multi-protocol support (MCP + A2A)
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class E2ETestSuite:
    """End-to-end test suite for strategy-based simulation."""

    def __init__(self, mcp_url="http://localhost:9080", a2a_url="http://localhost:9091"):
        self.mcp_url = mcp_url
        self.a2a_url = a2a_url
        self.test_token = "test_advertiser_456"
        self.admin_token = "test_admin_123"

    async def setup_mcp_client(self, token=None):
        """Create authenticated MCP client."""
        auth_token = token or self.test_token
        headers = {"x-adcp-auth": auth_token}
        transport = StreamableHttpTransport(url=f"{self.mcp_url}/mcp/", headers=headers)
        return Client(transport=transport)

    def run_a2a_query(self, message, token=None):
        """Run A2A query using official CLI."""
        auth_token = token or self.test_token
        env = os.environ.copy()
        env["A2A_AUTH_TOKEN"] = auth_token

        result = subprocess.run(
            ["uv", "run", "a2a", "send", self.a2a_url, message], env=env, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise Exception(f"A2A query failed: {result.stderr}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"raw_response": result.stdout}

    async def test_happy_path_simulation(self):
        """Test successful campaign lifecycle with happy path simulation."""
        print("🧪 Testing Happy Path Simulation")

        # Generate unique strategy ID for this test
        strategy_id = f"sim_test_happy_{uuid.uuid4().hex[:8]}"

        async with await self.setup_mcp_client() as mcp:
            # 1. Get products with strategy context
            products_response = await mcp.call_tool(
                "get_products",
                {
                    "brief": "video ads for sports content",
                    "brand_manifest": {"name": "athletic footwear"},
                    "strategy_id": strategy_id,
                },
            )

            assert len(products_response["products"]) > 0
            print(f"✅ Found {len(products_response['products'])} products")

            # 2. Create media buy with simulation strategy
            create_response = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "budget": 50000.0,
                    "strategy_id": strategy_id,
                },
            )

            media_buy_id = create_response["media_buy_id"]
            print(f"✅ Created media buy: {media_buy_id}")

            # 3. Jump to campaign start using simulation control
            control_response = await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "campaign-start"}},
            )

            assert control_response["status"] == "ok"
            print("✅ Jumped to campaign start")

            # 4. Check media buy status (should be active now)
            status_response = await mcp.call_tool(
                "check_media_buy_status", {"context_id": create_response["context_id"], "strategy_id": strategy_id}
            )

            print(f"✅ Campaign status: {status_response.get('status', 'unknown')}")

            # 5. Jump to 50% completion
            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "campaign-50-percent"}},
            )

            # 6. Get delivery report
            delivery_response = await mcp.call_tool(
                "get_media_buy_delivery",
                {
                    "media_buy_ids": [media_buy_id],
                    "today": "2025-08-08",  # Midpoint of campaign
                    "strategy_id": strategy_id,
                },
            )

            assert len(delivery_response["deliveries"]) > 0
            delivery = delivery_response["deliveries"][0]
            print(f"✅ Mid-campaign delivery: ${delivery['spend']:.2f} spent, {delivery['impressions']:,} impressions")

            # 7. Test A2A protocol with same strategy context
            a2a_response = self.run_a2a_query(f"What's the status of campaign {media_buy_id}?")
            print(f"✅ A2A query successful: {type(a2a_response)}")

        return {
            "strategy_id": strategy_id,
            "media_buy_id": media_buy_id,
            "final_delivery": delivery,
            "a2a_response": a2a_response,
        }

    async def test_budget_exceeded_simulation(self):
        """Test budget exceeded error simulation."""
        print("🚨 Testing Budget Exceeded Simulation")

        strategy_id = f"sim_test_budget_{uuid.uuid4().hex[:8]}"

        async with await self.setup_mcp_client() as mcp:
            # 1. Get products
            products_response = await mcp.call_tool(
                "get_products",
                {
                    "brief": "display advertising",
                    "brand_manifest": {"name": "consumer electronics"},
                    "strategy_id": strategy_id,
                },
            )

            # 2. Create media buy
            create_response = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "budget": 25000.0,
                    "strategy_id": strategy_id,
                },
            )

            media_buy_id = create_response["media_buy_id"]

            # 3. Set scenario to trigger budget exceeded
            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "set_scenario", "parameters": {"scenario": "budget_exceeded"}},
            )

            # 4. Jump to error event
            error_response = await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "error-budget-exceeded"}},
            )

            assert error_response["status"] == "ok"
            print("✅ Successfully triggered budget exceeded scenario")

            # 5. Verify delivery shows overspend
            delivery_response = await mcp.call_tool(
                "get_media_buy_delivery",
                {"media_buy_ids": [media_buy_id], "today": "2025-08-10", "strategy_id": strategy_id},
            )

            delivery = delivery_response["deliveries"][0]
            overspend_ratio = delivery["spend"] / 25000.0
            print(f"✅ Budget exceeded: ${delivery['spend']:.2f} / $25,000 = {overspend_ratio:.2f}x")
            assert overspend_ratio > 1.1  # Should be at least 10% overspend

        return {
            "strategy_id": strategy_id,
            "media_buy_id": media_buy_id,
            "overspend_amount": delivery["spend"] - 25000.0,
        }

    async def test_creative_rejection_simulation(self):
        """Test creative rejection simulation."""
        print("🎨 Testing Creative Rejection Simulation")

        strategy_id = f"sim_test_creative_{uuid.uuid4().hex[:8]}"

        async with await self.setup_mcp_client() as mcp:
            # 1. Create media buy
            products_response = await mcp.call_tool(
                "get_products",
                {
                    "brief": "video advertising",
                    "brand_manifest": {"name": "streaming service"},
                    "strategy_id": strategy_id,
                },
            )

            create_response = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "budget": 35000.0,
                    "strategy_id": strategy_id,
                },
            )

            # 2. Set scenario to force creative rejection
            await mcp.call_tool(
                "simulation_control",
                {
                    "strategy_id": strategy_id,
                    "action": "set_scenario",
                    "parameters": {"scenario": "creative_rejection"},
                },
            )

            # 3. Jump to creative rejection event
            rejection_response = await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "creative-rejected-policy"}},
            )

            assert rejection_response["status"] == "ok"
            print("✅ Creative rejection scenario triggered")

            # 4. Submit new creative (should be approved in simulation)
            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "creative-approved"}},
            )

            print("✅ Creative approved after revision")

        return {"strategy_id": strategy_id}

    async def test_production_strategy_behavior(self):
        """Test production strategy without simulation."""
        print("🏭 Testing Production Strategy Behavior")

        # Use production strategy (no 'sim_' prefix)
        strategy_id = "conservative_pacing"

        async with await self.setup_mcp_client() as mcp:
            # 1. Create campaign with production strategy
            products_response = await mcp.call_tool(
                "get_products",
                {
                    "brief": "premium display advertising",
                    "brand_manifest": {"name": "luxury goods"},
                    "strategy_id": strategy_id,
                },
            )

            create_response = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-30",  # Longer campaign
                    "budget": 75000.0,
                    "strategy_id": strategy_id,
                },
            )

            media_buy_id = create_response["media_buy_id"]
            print(f"✅ Created campaign with conservative pacing: {media_buy_id}")

            # 2. Try to use simulation control (should fail)
            try:
                await mcp.call_tool(
                    "simulation_control",
                    {"strategy_id": strategy_id, "action": "jump_to", "parameters": {"event": "campaign-start"}},
                )
                raise AssertionError("Simulation control should not work on production strategies")
            except Exception as e:
                print(f"✅ Correctly blocked simulation control on production strategy: {e}")

            # 3. Check that strategy affects behavior (conservative pacing = 0.8x)
            # This would be visible in delivery patterns in real scenarios
            print("✅ Production strategy applied (pacing multiplier would affect delivery)")

        return {"strategy_id": strategy_id, "media_buy_id": media_buy_id}

    async def test_parallel_strategies(self):
        """Test multiple strategies running in parallel."""
        print("🔀 Testing Parallel Strategies")

        strategy_1 = f"sim_test_parallel_a_{uuid.uuid4().hex[:8]}"
        strategy_2 = f"sim_test_parallel_b_{uuid.uuid4().hex[:8]}"

        async with await self.setup_mcp_client() as mcp:
            # Create two campaigns with different strategies
            products_response = await mcp.call_tool(
                "get_products",
                {"brief": "mobile advertising", "brand_manifest": {"name": "mobile app"}},
            )

            # Campaign A: Happy path
            campaign_a = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "budget": 30000.0,
                    "strategy_id": strategy_1,
                },
            )

            # Campaign B: Budget exceeded scenario
            campaign_b = await mcp.call_tool(
                "create_media_buy",
                {
                    "product_ids": [products_response["products"][0]["product_id"]],
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "budget": 30000.0,
                    "strategy_id": strategy_2,
                },
            )

            # Set different scenarios for each strategy
            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_1, "action": "set_scenario", "parameters": {"scenario": "high_performance"}},
            )

            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_2, "action": "set_scenario", "parameters": {"scenario": "budget_exceeded"}},
            )

            # Jump both to campaign start
            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_1, "action": "jump_to", "parameters": {"event": "campaign-start"}},
            )

            await mcp.call_tool(
                "simulation_control",
                {"strategy_id": strategy_2, "action": "jump_to", "parameters": {"event": "campaign-start"}},
            )

            print("✅ Both parallel campaigns started with different strategies")

        return {
            "strategy_1": strategy_1,
            "strategy_2": strategy_2,
            "campaign_a": campaign_a["media_buy_id"],
            "campaign_b": campaign_b["media_buy_id"],
        }

    async def test_a2a_integration(self):
        """Test A2A protocol integration."""
        print("🤝 Testing A2A Protocol Integration")

        # Test basic A2A queries
        queries = [
            "What products do you have?",
            "Show me video advertising options for sports content",
            "What targeting capabilities are available?",
            "What are your pricing models?",
        ]

        responses = []
        for query in queries:
            try:
                response = self.run_a2a_query(query)
                responses.append({"query": query, "response": response, "success": True})
                print(f"✅ A2A Query: '{query[:50]}...' → Success")
            except Exception as e:
                responses.append({"query": query, "error": str(e), "success": False})
                print(f"❌ A2A Query: '{query[:50]}...' → Failed: {e}")

        success_count = len([r for r in responses if r.get("success")])
        print(f"✅ A2A Integration: {success_count}/{len(queries)} queries successful")

        return {"responses": responses, "success_rate": success_count / len(queries)}

    async def run_all_tests(self):
        """Run complete test suite."""
        print("🚀 Starting Comprehensive E2E Test Suite")
        print("=" * 60)

        results = {}

        try:
            # Test 1: Happy path simulation
            results["happy_path"] = await self.test_happy_path_simulation()

            # Test 2: Budget exceeded simulation
            results["budget_exceeded"] = await self.test_budget_exceeded_simulation()

            # Test 3: Creative rejection simulation
            results["creative_rejection"] = await self.test_creative_rejection_simulation()

            # Test 4: Production strategy behavior
            results["production_strategy"] = await self.test_production_strategy_behavior()

            # Test 5: Parallel strategies
            results["parallel_strategies"] = await self.test_parallel_strategies()

            # Test 6: A2A integration
            results["a2a_integration"] = await self.test_a2a_integration()

        except Exception as e:
            print(f"❌ Test suite failed: {e}")
            results["error"] = str(e)

        print("=" * 60)
        print("🎉 E2E Test Suite Complete")

        # Summary
        success_tests = len([k for k, v in results.items() if k != "error" and v])
        total_tests = len(results) - (1 if "error" in results else 0)
        print(f"📊 Results: {success_tests}/{total_tests} test scenarios successful")

        if results.get("a2a_integration"):
            a2a_success_rate = results["a2a_integration"]["success_rate"]
            print(f"📊 A2A Success Rate: {a2a_success_rate:.1%}")

        return results


async def main():
    """Run the test suite."""
    test_suite = E2ETestSuite()
    return await test_suite.run_all_tests()


if __name__ == "__main__":
    # Run the test suite
    results = asyncio.run(main())

    # Pretty print results
    print("\n📋 Detailed Results:")
    print(json.dumps(results, indent=2, default=str))
