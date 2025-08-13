#!/usr/bin/env python3
"""Final test of MCP client with correct parameters."""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_mcp_call():
    """Test the MCP call with correct parameter format and token."""
    
    # Use the actual token from the database
    headers = {
        "x-adcp-auth": "token_6119345e4a080d7223ee631062ca0e9e",
        "x-adcp-tenant": "test_publisher"
    }
    
    server_url = "http://localhost:8005/mcp/"
    
    transport = StreamableHttpTransport(server_url, headers=headers)
    
    async with Client(transport) as client:
        try:
            # Call with parameters wrapped in 'req' as expected by FastMCP
            print("Testing get_products with wrapped parameters...")
            params = {"req": {"brief": "test products"}}
            result = await client.call_tool("get_products", params)
            
            # Handle CallToolResult properly
            print(f"Result type: {type(result)}")
            print(f"Result content: {result}")
            
            if hasattr(result, 'content'):
                if hasattr(result.content, 'model_dump'):
                    result_dict = result.content.model_dump()
                else:
                    result_dict = result.content
            elif hasattr(result, 'model_dump'):
                result_dict = result.model_dump()
            else:
                result_dict = result
                
            print(f"✅ Success! Result: {result_dict}")
            if isinstance(result_dict, dict) and result_dict.get('products'):
                print(f"Got {len(result_dict.get('products', []))} products")
                print(f"\nFirst product:")
                print(json.dumps(result_dict['products'][0], indent=2))
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_call())
    exit(0 if success else 1)