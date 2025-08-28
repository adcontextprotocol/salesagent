#!/usr/bin/env python3
"""
Debug script to run E2E tests with full request/response logging.
This shows exactly what data is being sent back and forth.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tests.e2e.test_adcp_full_lifecycle import AdCPTestClient


class DebugTestClient(AdCPTestClient):
    """Enhanced test client with detailed request/response logging."""

    async def call_mcp_tool(self, tool_name: str, params: dict) -> dict:
        """Call MCP tool with detailed logging."""
        print(f"\n🔵 MCP REQUEST: {tool_name}")
        print(f"   URL: {self.mcp_url}/mcp/")
        print(f"   Headers: {json.dumps(self._build_headers(), indent=2)}")
        print(f"   Params: {json.dumps(params, indent=2)}")

        try:
            result = await self.mcp_client.call_tool(tool_name, {"req": params})

            # Use the robust parsing from the parent class
            response_data = self._parse_mcp_response(result)
            print(f"🟢 MCP RESPONSE: {tool_name}")
            print(f"   Response: {json.dumps(response_data, indent=2)}")
            return response_data

        except Exception as e:
            print(f"🔴 MCP ERROR: {tool_name} - {e}")
            raise

    async def query_a2a(self, query: str) -> dict:
        """Query A2A with detailed logging."""
        print("\n🔵 A2A REQUEST:")
        print(f"   URL: {self.a2a_url}/message")
        print(f"   Query: {query}")

        headers = self._build_headers()
        headers["Authorization"] = f"Bearer {self.auth_token}"
        print(f"   Headers: {json.dumps(headers, indent=2)}")

        payload = {"message": query, "thread_id": self.test_session_id}
        print(f"   Payload: {json.dumps(payload, indent=2)}")

        try:
            response = await self.http_client.post(
                f"{self.a2a_url}/message",
                json=payload,
                headers=headers,
                timeout=10.0,
            )

            response.raise_for_status()
            response_data = response.json()

            print("🟢 A2A RESPONSE:")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {json.dumps(response_data, indent=2)}")

            return response_data

        except Exception as e:
            print(f"🔴 A2A ERROR: {query} - {e}")
            raise


async def run_debug_test():
    """Run a simple debug test to see the protocol in action."""
    print("🚀 Starting AdCP E2E Debug Test")
    print("=" * 60)

    # Use the same ports as the test configuration from environment variables
    import os

    mcp_port = os.getenv("ADCP_SALES_PORT", "8166")
    a2a_port = os.getenv("A2A_PORT", "8091")

    mcp_url = f"http://localhost:{mcp_port}"
    a2a_url = f"http://localhost:{a2a_port}"
    auth_token = "7HP-ulnyvAxALOuYPMeDujwKjwjgfUpriSuXAzfKa5c"  # Valid test token created in database

    print(f"MCP Server: {mcp_url}")
    print(f"A2A Server: {a2a_url}")
    print(f"Auth Token: {auth_token}")

    async with DebugTestClient(mcp_url, a2a_url, auth_token, dry_run=True) as client:

        try:
            # Test 1: Product Discovery
            print(f"\n{'='*60}")
            print("🧪 TEST 1: Product Discovery")
            print(f"{'='*60}")

            products = await client.call_mcp_tool(
                "get_products", {"brief": "Looking for display advertising", "promoted_offering": "test campaign"}
            )

            if products and "products" in products:
                print(f"✅ Found {len(products['products'])} products")
                for i, product in enumerate(products["products"][:2]):  # Show first 2
                    print(f"   Product {i+1}: {product.get('name', 'Unnamed')}")
                    print(f"   ID: {product.get('product_id', product.get('id', 'N/A'))}")

            # Test 2: A2A Query
            print(f"\n{'='*60}")
            print("🧪 TEST 2: A2A Product Query")
            print(f"{'='*60}")

            a2a_response = await client.query_a2a("What display advertising products do you offer?")

            if a2a_response and "status" in a2a_response:
                print(f"✅ A2A Query completed with status: {a2a_response['status']['state']}")

            # Test 3: Media Buy Creation
            if products and "products" in products and len(products["products"]) > 0:
                print(f"\n{'='*60}")
                print("🧪 TEST 3: Media Buy Creation")
                print(f"{'='*60}")

                product_id = products["products"][0].get("product_id", products["products"][0].get("id"))

                media_buy = await client.call_mcp_tool(
                    "create_media_buy",
                    {
                        "product_ids": [product_id],
                        "budget": 5000.0,
                        "start_date": "2025-09-01",
                        "end_date": "2025-09-30",
                    },
                )

                if media_buy and "media_buy_id" in media_buy:
                    print(f"✅ Created media buy: {media_buy['media_buy_id']}")
                    print(f"   Status: {media_buy.get('status', 'N/A')}")
                    print(f"   Budget: ${media_buy.get('budget', 'N/A')}")

            print(f"\n{'='*60}")
            print("🎉 Debug test completed successfully!")
            print(f"{'='*60}")

        except Exception as e:
            print(f"\n❌ Debug test failed: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_debug_test())
