#!/usr/bin/env python3
"""Test script to verify MCP client parameter format."""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_mcp_call():
    """Test different parameter formats."""
    
    headers = {
        "x-adcp-auth": "test_token_123",
        "x-adcp-tenant": "default"
    }
    
    server_url = "http://localhost:8005/mcp/"
    transport = StreamableHttpTransport(server_url, headers=headers)
    
    async with Client(transport) as client:
        # Test 1: Parameters wrapped in 'req'
        print("Test 1: Parameters wrapped in 'req'...")
        try:
            params = {"req": {"brief": "test products"}}
            result = await client.call_tool("get_products", params)
            print("✅ Success with wrapped params!")
        except Exception as e:
            print(f"❌ Failed: {e}")
            
        # Test 2: Direct parameters with 'brief' key
        print("\nTest 2: Direct parameters...")
        try:
            params = {"brief": "test products"}
            result = await client.call_tool("get_products", params)
            print("✅ Success with direct params!")
        except Exception as e:
            print(f"❌ Failed: {e}")
            
        # Test 3: Check what tools are available
        print("\nTest 3: List available tools...")
        try:
            tools = await client.list_tools()
            print(f"Available tools: {[t.name for t in tools]}")
            
            # Find get_products tool
            get_products_tool = next((t for t in tools if t.name == "get_products"), None)
            if get_products_tool:
                print(f"\nget_products schema:")
                print(json.dumps(get_products_tool.model_dump(), indent=2))
        except Exception as e:
            print(f"❌ Failed to list tools: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_call())