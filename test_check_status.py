#!/usr/bin/env python3
"""Test check_media_buy_status request"""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_check_status():
    """Test the check_media_buy_status tool"""
    
    # Configure client
    headers = {"x-adcp-auth": "LLNFcWBNDrCj_kxdv0sfNq7jQoOYZ3N1oYxhQ8WFvLs"}
    transport = StreamableHttpTransport(
        url="http://localhost:8005/mcp/",
        headers=headers
    )
    client = Client(transport=transport)
    
    try:
        async with client:
            print("Testing check_media_buy_status...")
            
            # Use the context_id from the previous test
            result = await client.call_tool(
                "check_media_buy_status",
                {
                    "req": {
                        "context_id": "ctx_1cf9bd8f6e55"
                    }
                }
            )
            
            print("Success! Response:")
            if hasattr(result, 'structured_content'):
                print(json.dumps(result.structured_content, indent=2))
            else:
                print(json.dumps(result, indent=2, default=str))
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_check_status())