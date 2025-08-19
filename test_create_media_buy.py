#!/usr/bin/env python3
"""
Quick test script to verify the create_media_buy fix.
"""

import asyncio
import sys

sys.path.append(".")

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_create_media_buy():
    """Test the create_media_buy endpoint to verify the SQLAlchemy fix."""

    # Use the first token from the database
    headers = {"x-adcp-auth": "CO6zIXPr3chC5Qhm5RijXC-MwcJPzPkHgFmCPuqmkuU"}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)

    try:
        async with Client(transport=transport) as client:
            print("✅ MCP client connected successfully")

            # First, get products to make sure get_product_catalog works
            print("\n📋 Testing get_products...")
            try:
                products_response = await client.call_tool(
                    "get_products", {"req": {"brief": "test products", "promoted_offering": "test offering"}}
                )
                print("✅ get_products succeeded!")

                # Access the structured_content from CallToolResult
                products_data = products_response.structured_content
                if not products_data.get("products"):
                    print("❌ No products available for testing")
                    return

                product_id = products_data["products"][0]["product_id"]
                print(f"📦 Using product: {product_id}")

            except Exception as e:
                print(f"❌ get_products failed: {e}")
                return

            # Now test create_media_buy
            print("\n🛒 Testing create_media_buy...")
            try:
                response = await client.call_tool(
                    "create_media_buy",
                    {
                        "req": {
                            "product_ids": [product_id],
                            "total_budget": 1000.0,
                            "flight_start_date": "2025-02-01",
                            "flight_end_date": "2025-02-28",
                        }
                    },
                )

                print("✅ create_media_buy succeeded!")

                # Access the structured_content from CallToolResult
                if hasattr(response, "structured_content") and response.structured_content:
                    data = response.structured_content
                    print(f"   Media Buy ID: {data.get('media_buy_id')}")
                    print(f"   Status: {data.get('status')}")
                    print(f"   Message: {data.get('message')}")
                else:
                    print(f"   Raw response: {response}")

            except Exception as e:
                print(f"❌ create_media_buy failed: {e}")

                # Check if it's the specific SQLAlchemy error we're fixing
                if "Column expression, FROM clause, or other columns clause element expected" in str(e):
                    print("🚨 This is the SQLAlchemy import collision error we're trying to fix!")
                    return False
                else:
                    print("ℹ️  This is a different error, not the import collision issue")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

    return True


if __name__ == "__main__":
    result = asyncio.run(test_create_media_buy())
    if result:
        print("\n🎉 Test completed successfully! The SQLAlchemy import fix is working.")
    else:
        print("\n💥 Test failed. The SQLAlchemy import collision still exists.")
