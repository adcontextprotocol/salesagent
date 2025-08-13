#!/usr/bin/env python3
"""
Test the proper AdCP workflow:
1. create_media_buy -> returns context_id
2. check_media_buy_status using context_id -> shows pending_creative
3. add_creative_assets (submit_creatives) -> attaches creatives
4. check_media_buy_status -> shows active/live
5. get_media_buy_delivery -> pull reporting
"""

import asyncio
import json
from datetime import datetime, timedelta
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_adcp_workflow():
    """Test the complete AdCP workflow."""
    
    # Setup client
    headers = {
        "x-adcp-auth": "token_6119345e4a080d7223ee631062ca0e9e",
        "x-adcp-tenant": "test_publisher"
    }
    transport = StreamableHttpTransport("http://localhost:8005/mcp/", headers=headers)
    
    print("🚀 Testing AdCP Workflow")
    print("=" * 60)
    
    async with Client(transport) as client:
        # Step 1: Get products
        print("\n1️⃣ Getting products...")
        result = await client.call_tool('get_products', {
            'req': {
                'brief': 'Display advertising for homepage',
                'promoted_offering': 'Test Brand Campaign'
            }
        })
        products = result.structured_content['products']
        print(f"   Found {len(products)} products")
        if products:
            product_id = products[0]['product_id']
            print(f"   Using product: {product_id}")
        else:
            print("   ❌ No products found!")
            return
        
        # Step 2: Create media buy
        print("\n2️⃣ Creating media buy...")
        flight_start = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        flight_end = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        
        result = await client.call_tool('create_media_buy', {
            'req': {
                'product_ids': [product_id],
                'flight_start_date': flight_start,
                'flight_end_date': flight_end,
                'total_budget': 5000.0,
                'targeting_overlay': {
                    'geo_country_any_of': ['US']
                }
            }
        })
        
        create_response = result.structured_content
        context_id = create_response.get('context_id')
        media_buy_id = create_response.get('media_buy_id')
        initial_status = create_response.get('status', 'unknown')
        
        print(f"   ✅ Media Buy Created!")
        print(f"   Media Buy ID: {media_buy_id}")
        print(f"   Context ID: {context_id}")
        print(f"   Initial Status: {initial_status}")
        
        if not context_id:
            print("   ❌ No context_id returned! Cannot continue.")
            return
        
        # Step 3: Check status (should be pending_creative)
        print("\n3️⃣ Checking media buy status...")
        result = await client.call_tool('check_media_buy_status', {
            'req': {
                'context_id': context_id
            }
        })
        
        status_response = result.structured_content
        print(f"   Status: {status_response.get('status')}")
        print(f"   Creative Count: {status_response.get('creative_count', 0)}")
        print(f"   Detail: {status_response.get('detail', 'N/A')}")
        
        # Step 4: Add creative assets
        print("\n4️⃣ Adding creative assets...")
        result = await client.call_tool('add_creative_assets', {
            'req': {
                'media_buy_id': media_buy_id,
                'creatives': [{
                    'creative_id': f'creative_{datetime.now().timestamp()}',
                    'principal_id': 'princ_435d8979',
                    'format_id': 'display_300x250',
                    'name': 'Test Creative',
                    'content_uri': 'https://example.com/creative.jpg',
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }]
            }
        })
        
        creative_response = result.structured_content
        print(f"   ✅ Creative submitted")
        print(f"   Response: {creative_response}")
        
        # Step 5: Check status again (should be active/live)
        print("\n5️⃣ Checking status after creative submission...")
        await asyncio.sleep(1)  # Small delay to allow processing
        
        result = await client.call_tool('check_media_buy_status', {
            'req': {
                'context_id': context_id
            }
        })
        
        status_response = result.structured_content
        print(f"   Status: {status_response.get('status')}")
        print(f"   Creative Count: {status_response.get('creative_count', 0)}")
        print(f"   Budget Remaining: ${status_response.get('budget_remaining', 0):.2f}")
        
        # Step 6: Get delivery/reporting
        print("\n6️⃣ Getting media buy delivery (reporting)...")
        result = await client.call_tool('get_media_buy_delivery', {
            'req': {
                'media_buy_id': media_buy_id,
                'today': datetime.now().strftime('%Y-%m-%d')
            }
        })
        
        delivery_response = result.structured_content
        print(f"   Total Spend: ${delivery_response.get('total_spend', 0):.2f}")
        print(f"   Total Impressions: {delivery_response.get('total_impressions', 0):,}")
        
        print("\n" + "=" * 60)
        print("✅ AdCP Workflow Test Complete!")
        print("\nKey Takeaways:")
        print("- context_id is used for status checking (not media_buy_id)")
        print("- Status transitions: pending_creative → active (after creatives)")
        print("- get_principal_summary is NOT part of AdCP spec")
        print("- This is the spec-compliant workflow")

if __name__ == "__main__":
    asyncio.run(test_adcp_workflow())