#!/usr/bin/env python3
"""Test script to verify MCP client fix."""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_mcp_call():
    """Test the MCP call with correct parameter format."""
    
    # Use the default test token
    headers = {
        "x-adcp-auth": "test_token_123",
        "x-adcp-tenant": "default"
    }
    
    server_url = "http://localhost:8005/mcp/"
    
    transport = StreamableHttpTransport(server_url, headers=headers)
    
    async with Client(transport) as client:
        try:
            # Test 1: Call with parameters directly (not wrapped in 'req')
            print("Testing get_products with parameters...")
            params = {"brief": "test products"}
            result = await client.call_tool("get_products", params)
            
            if hasattr(result, 'model_dump'):
                result_dict = result.model_dump()
            else:
                result_dict = result
                
            print(f"✅ Success! Got {len(result_dict.get('products', []))} products")
            print(f"First product: {json.dumps(result_dict['products'][0] if result_dict.get('products') else {}, indent=2)}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Error type: {type(e).__name__}")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_call())
    exit(0 if success else 1)