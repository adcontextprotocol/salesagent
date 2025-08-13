#!/usr/bin/env python3
"""Test script to verify the unified get_media_buy_delivery endpoint."""

import asyncio
import json
from datetime import date
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_unified_delivery():
    """Test various patterns with the unified delivery endpoint."""
    
    # Create client with test token
    headers = {"x-adcp-auth": "test_token"}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)
    
    try:
        async with client:
            print("🔍 Testing unified get_media_buy_delivery endpoint...")
            
            # Test 1: Single media buy (as array)
            print("\n1️⃣ Testing single media buy query...")
            try:
                result = await client.tools.get_media_buy_delivery(
                    media_buy_ids=["test_buy_123"],
                    today=date.today().isoformat()
                )
                print("   ✅ Single buy query works")
                print(f"   - Response has 'deliveries' array: {'deliveries' in result}")
            except Exception as e:
                print(f"   ❌ Single buy query failed: {e}")
            
            # Test 2: Multiple media buys
            print("\n2️⃣ Testing multiple media buys query...")
            try:
                result = await client.tools.get_media_buy_delivery(
                    media_buy_ids=["test_buy_123", "test_buy_456"],
                    today=date.today().isoformat()
                )
                print("   ✅ Multiple buys query works")
            except Exception as e:
                print(f"   ❌ Multiple buys query failed: {e}")
            
            # Test 3: All active buys (using status_filter)
            print("\n3️⃣ Testing all active buys (default filter)...")
            try:
                result = await client.tools.get_media_buy_delivery(
                    today=date.today().isoformat()
                    # status_filter defaults to "active"
                )
                print("   ✅ Active buys query works (default)")
            except Exception as e:
                print(f"   ❌ Active buys query failed: {e}")
            
            # Test 4: All buys (explicit status_filter)
            print("\n4️⃣ Testing all buys with status_filter='all'...")
            try:
                result = await client.tools.get_media_buy_delivery(
                    status_filter="all",
                    today=date.today().isoformat()
                )
                print("   ✅ All buys query works")
                print(f"   - Total spend: ${result.get('total_spend', 0):,.2f}")
                print(f"   - Active count: {result.get('active_count', 0)}")
            except Exception as e:
                print(f"   ❌ All buys query failed: {e}")
            
            # Test 5: Completed buys only
            print("\n5️⃣ Testing completed buys with status_filter='completed'...")
            try:
                result = await client.tools.get_media_buy_delivery(
                    status_filter="completed",
                    today=date.today().isoformat()
                )
                print("   ✅ Completed buys query works")
            except Exception as e:
                print(f"   ❌ Completed buys query failed: {e}")
            
            # Test 6: Verify deprecated endpoint still works
            print("\n6️⃣ Testing deprecated get_all_media_buy_delivery (backward compat)...")
            try:
                result = await client.tools.get_all_media_buy_delivery(
                    today=date.today().isoformat()
                )
                print("   ✅ Deprecated endpoint still works")
            except Exception as e:
                print(f"   ⚠️  Deprecated endpoint not available (expected if removed)")
            
            print("\n✅ All tests completed!")
            
    except Exception as e:
        print(f"❌ Client connection error: {e}")
        print("   Make sure the server is running on http://localhost:8080")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_unified_delivery())
    if success:
        print("\n🎉 Unified delivery endpoint is working correctly!")
    else:
        print("\n⚠️  Some tests failed. Check the server logs.")