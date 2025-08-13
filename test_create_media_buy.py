#!/usr/bin/env python3
"""Test create_media_buy request"""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_create_media_buy():
    """Test the create_media_buy tool"""
    
    # Configure client
    headers = {"x-adcp-auth": "LLNFcWBNDrCj_kxdv0sfNq7jQoOYZ3N1oYxhQ8WFvLs"}
    transport = StreamableHttpTransport(
        url="http://localhost:8005/mcp/",
        headers=headers
    )
    client = Client(transport=transport)
    
    try:
        async with client:
            print("Testing create_media_buy...")
            
            # Call create_media_buy
            result = await client.call_tool(
                "create_media_buy",
                {
                    "req": {
                        "product_ids": ["ros_display_us"],
                        "flight_start_date": "2025-08-20",
                        "flight_end_date": "2025-09-12",
                        "total_budget": 5000.0,
                        "targeting_overlay": {
                            "geo_country_any_of": ["US"]
                        }
                    }
                }
            )
            
            print("Success! Response:")
            print(json.dumps(result, indent=2, default=str))
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_create_media_buy())