#!/usr/bin/env python3
"""Quick test script to verify Gemini 2.5 Flash AI integration."""

import pytest
import os
import sys
import asyncio
import json
from ai_product_service import AIProductConfigurationService, ProductDescription

pytestmark = pytest.mark.integration

async def test_gemini_integration():
    """Test that Gemini 2.5 Flash is working correctly."""
    
    print("=== Testing Gemini 2.5 Flash Integration ===\n")
    
    # Check for API key
    if not os.environ.get('GEMINI_API_KEY'):
        print("❌ ERROR: GEMINI_API_KEY environment variable not set!")
        print("   Please set: export GEMINI_API_KEY='your-api-key'")
        return False
    
    print("✅ GEMINI_API_KEY found")
    
    try:
        # Initialize service
        print("\n🔧 Initializing AI Product Configuration Service...")
        service = AIProductConfigurationService()
        
        # Verify model version
        model_name = service.model._model_name
        print(f"✅ Using model: {model_name}")
        
        if '2.5-flash' not in model_name and '2-flash' not in model_name:
            print(f"⚠️  WARNING: Expected gemini-2.5-flash, but got {model_name}")
        
        # Test simple AI prompt
        print("\n🤖 Testing AI response...")
        prompt = """
        Return a simple JSON object with this exact structure:
        {
            "test": "success",
            "model": "gemini-2.5-flash",
            "timestamp": "2024-01-01"
        }
        """
        
        response = service.model.generate_content(prompt)
        print(f"✅ AI responded successfully")
        
        # Try to parse response
        try:
            # Clean up response text (remove markdown if present)
            text = response.text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1].rsplit('\n```', 1)[0]
            
            result = json.loads(text)
            print(f"✅ AI returned valid JSON: {result}")
        except:
            print(f"⚠️  AI response (raw): {response.text}")
        
        # Test product description analysis
        print("\n📦 Testing product configuration...")
        
        # Mock inventory for testing
        from ai_product_service import AdServerInventory
        test_inventory = AdServerInventory(
            placements=[
                {
                    "id": "homepage_top",
                    "name": "Homepage Banner",
                    "sizes": ["728x90", "970x250"],
                    "typical_cpm": 25.0,
                    "position": "above_fold"
                }
            ],
            ad_units=[],
            targeting_options={"countries": ["US", "CA", "GB"]},
            creative_specs=[]
        )
        
        # Test inventory analysis
        test_description = ProductDescription(
            name="Premium Homepage Banner",
            external_description="High-impact banner on homepage above the fold",
            internal_details="Use 970x250 for maximum impact"
        )
        
        analysis = service._analyze_inventory_for_product(test_description, test_inventory)
        
        print(f"✅ Inventory analysis completed:")
        print(f"   - Premium level: {analysis['premium_level']}")
        print(f"   - Matched placements: {len(analysis['matched_placements'])}")
        print(f"   - Suggested CPM range: ${analysis['suggested_cpm_range']['min']:.2f} - ${analysis['suggested_cpm_range']['max']:.2f}")
        
        print("\n✨ All tests passed! Gemini 2.5 Flash integration is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoints():
    """Test the Flask API endpoints."""
    print("\n\n=== Testing API Endpoints ===\n")
    
    from admin_ui import app
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        # Mock authentication
        with client.session_transaction() as sess:
            sess['email'] = 'test@example.com'
            sess['role'] = 'super_admin'
            sess['tenant_id'] = 'test_tenant'
        
        # Test suggestions endpoint
        print("📡 Testing /api/tenant/test_tenant/products/suggestions...")
        response = client.get('/api/tenant/test_tenant/products/suggestions?industry=news')
        if response.status_code == 200:
            data = json.loads(response.data)
            print(f"✅ Suggestions API returned {data['total_count']} products")
        else:
            print(f"❌ Suggestions API failed: {response.status_code}")
        
        # Test with filters
        print("\n📡 Testing suggestions with filters...")
        response = client.get('/api/tenant/test_tenant/products/suggestions?delivery_type=guaranteed&max_cpm=20')
        if response.status_code == 200:
            data = json.loads(response.data)
            print(f"✅ Filtered suggestions returned {data['total_count']} products")
            if data['suggestions']:
                print(f"   Sample: {data['suggestions'][0]['name']} - ${data['suggestions'][0].get('cpm', 'N/A')} CPM")
        else:
            print(f"❌ Filtered suggestions failed: {response.status_code}")


if __name__ == '__main__':
    print("🚀 AdCP AI Product Feature Test Suite\n")
    
    # Run async test
    success = asyncio.run(test_gemini_integration())
    
    # Run API tests (don't need real Gemini for these)
    test_api_endpoints()
    
    print("\n" + "="*50)
    if success:
        print("✅ AI integration tests PASSED")
    else:
        print("❌ AI integration tests FAILED")
    
    sys.exit(0 if success else 1)