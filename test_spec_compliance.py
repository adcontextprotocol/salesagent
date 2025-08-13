#!/usr/bin/env python3
"""Test script to verify AdCP spec compliance after removing non-spec tools."""

import asyncio
import sys
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_spec_compliance():
    """Test that only AdCP-compliant tools are exposed."""
    
    # Create client with test token
    headers = {"x-adcp-auth": "test_token"}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)
    
    try:
        async with client:
            # List all available tools
            print("🔍 Checking available MCP tools...")
            
            # Get server capabilities (this will show available tools)
            capabilities = await client.initialize()
            
            if capabilities and hasattr(capabilities, 'tools'):
                tool_names = [tool.name for tool in capabilities.tools]
                
                print(f"\n✅ Found {len(tool_names)} tools:")
                for name in sorted(tool_names):
                    print(f"   - {name}")
                
                # Check for non-spec tool
                if "get_principal_summary" in tool_names:
                    print("\n❌ ERROR: get_principal_summary still exposed (not part of AdCP spec)")
                    return False
                else:
                    print("\n✅ get_principal_summary correctly removed")
                
                # Check for correct creative tool
                if "add_creative_assets" in tool_names:
                    print("✅ add_creative_assets correctly exposed")
                else:
                    print("❌ ERROR: add_creative_assets not found")
                    return False
                    
                if "submit_creatives" in tool_names:
                    print("❌ ERROR: submit_creatives found (should be add_creative_assets)")
                    return False
                else:
                    print("✅ submit_creatives not present (correct)")
                    
                return True
            else:
                print("❌ Could not get server capabilities")
                return False
                
    except Exception as e:
        print(f"❌ Error connecting to server: {e}")
        print("   Make sure the server is running on http://localhost:8080")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_spec_compliance())
    sys.exit(0 if success else 1)