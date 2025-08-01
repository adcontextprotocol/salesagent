#!/usr/bin/env python3
"""Test UI testing subagent via MCP client."""

import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def main():
    """Test the UI testing subagent."""
    print("🧪 Testing UI Testing Subagent via MCP\n")
    
    # Create MCP client
    transport = StreamableHttpTransport(url="http://localhost:8090/mcp/")
    client = Client(transport=transport)
    
    async with client:
        # Test 1: List available tests
        print("1. Listing available UI tests...")
        try:
            tests = await client.tools.list_ui_tests()
            print(f"✅ Found test files:")
            for test_file, functions in list(tests.items())[:3]:
                print(f"   - {test_file}: {len(functions)} tests")
        except Exception as e:
            print(f"❌ Failed: {e}")
        
        print()
        
        # Test 2: Check auth status
        print("2. Checking authentication status...")
        try:
            auth = await client.tools.check_auth_status()
            print(f"✅ Auth status:")
            print(f"   - Logged in: {auth.get('logged_in', False)}")
            print(f"   - Email: {auth.get('email', 'N/A')}")
            print(f"   - Role: {auth.get('role', 'N/A')}")
        except Exception as e:
            print(f"❌ Failed: {e}")
        
        print()
        
        # Test 3: Run a basic test
        print("3. Running a basic browser test...")
        try:
            result = await client.tools.run_ui_test(
                test_path="tests/test_basic_setup.py::TestBasicSetup::test_browser_launches",
                headed=False,
                timeout=30
            )
            print(f"✅ Test result:")
            print(f"   - Success: {result.get('success', False)}")
            print(f"   - Exit code: {result.get('exit_code', 'N/A')}")
            if result.get('screenshots'):
                print(f"   - Screenshots: {len(result['screenshots'])}")
        except Exception as e:
            print(f"❌ Failed: {e}")
    
    print("\n✨ MCP client test complete!")


if __name__ == "__main__":
    asyncio.run(main())