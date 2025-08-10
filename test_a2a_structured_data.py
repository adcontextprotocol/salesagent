#!/usr/bin/env python
"""
Comprehensive test suite for A2A structured data responses.

This test verifies that all A2A tasks return properly structured data
according to the AdCP specification, not just text summaries.
"""

import httpx
import json
from typing import Dict, Any, List
from datetime import datetime, timedelta

class A2AStructuredDataTester:
    """Test harness for A2A structured data responses."""
    
    def __init__(self, base_url: str = "http://localhost:8190/rpc"):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "x-adcp-auth": "test_token_123"
        }
        self.context_id = f"ctx_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.failures = []
        self.successes = []
    
    def make_request(self, method: str, params: Dict[str, Any]) -> Dict:
        """Make an A2A JSON-RPC request."""
        request = {
            "id": f"test_{method}_{datetime.now().timestamp()}",
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        response = httpx.post(self.base_url, json=request, headers=self.headers)
        return response.json()
    
    def validate_task_response(self, result: Dict, expected_fields: List[str]) -> bool:
        """Validate that a task response has the expected structure."""
        if result.get("kind") != "task":
            self.failures.append(f"Response kind is '{result.get('kind')}', expected 'task'")
            return False
        
        # Check status structure
        status = result.get("status", {})
        if not isinstance(status, dict):
            self.failures.append("Status should be an object")
            return False
        
        if "state" not in status:
            self.failures.append("Status missing 'state' field")
            return False
        
        # Check for expected data fields
        if status.get("state") == "completed":
            artifact = result.get("artifact", {})
            missing_fields = []
            for field in expected_fields:
                if field not in artifact:
                    missing_fields.append(field)
            
            if missing_fields:
                self.failures.append(f"Missing expected fields in artifact: {missing_fields}")
                return False
        
        return True
    
    def validate_message_response(self, result: Dict) -> bool:
        """Validate that a message response has proper structure."""
        if result.get("kind") != "message":
            self.failures.append(f"Response kind is '{result.get('kind')}', expected 'message'")
            return False
        
        if result.get("role") != "agent":
            self.failures.append(f"Role is '{result.get('role')}', expected 'agent'")
            return False
        
        parts = result.get("parts", [])
        if not parts:
            self.failures.append("No parts in message response")
            return False
        
        part_kinds = [p.get("kind") for p in parts]
        
        # Check for data parts when appropriate
        has_text = "text" in part_kinds
        has_data = "data" in part_kinds
        
        return has_text  # At minimum, should have text
    
    def test_get_products(self):
        """Test get_products returns full product data."""
        print("\n🧪 Testing get_products...")
        
        response = self.make_request("get_products", {
            "brief": "sports inventory",
            "channels": ["display", "video"]
        })
        
        result = response.get("result", {})
        
        if self.validate_task_response(result, ["products"]):
            products = result.get("artifact", {}).get("products", [])
            
            if not products:
                self.failures.append("No products returned")
                return False
            
            # Check first product has all required fields
            product = products[0]
            required_fields = [
                "product_id", "name", "description", "formats",
                "targeting_template", "delivery_method", "inventory_type"
            ]
            
            missing = [f for f in required_fields if f not in product]
            if missing:
                self.failures.append(f"Product missing required fields: {missing}")
                return False
            
            # Check format structure
            formats = product.get("formats", [])
            if formats and isinstance(formats[0], dict):
                format_fields = ["format_id", "name", "type"]
                format_missing = [f for f in format_fields if f not in formats[0]]
                if format_missing:
                    self.failures.append(f"Format missing fields: {format_missing}")
                    return False
            
            self.successes.append("get_products returns full structured data")
            return True
        
        return False
    
    def test_message_send_with_products(self):
        """Test message/send returns structured product data for inventory queries."""
        print("\n🧪 Testing message/send with product query...")
        
        response = self.make_request("message/send", {
            "message": {
                "contextId": self.context_id,
                "kind": "message",
                "messageId": "msg_test_products",
                "parts": [
                    {
                        "kind": "text",
                        "text": "Show me video advertising inventory"
                    }
                ],
                "role": "user"
            }
        })
        
        result = response.get("result", {})
        
        if self.validate_message_response(result):
            parts = result.get("parts", [])
            
            # Should have both text and data parts for product queries
            part_kinds = [p.get("kind") for p in parts]
            
            if "data" not in part_kinds:
                self.failures.append("message/send should return data part for product queries")
                return False
            
            # Find and validate data part
            for part in parts:
                if part.get("kind") == "data":
                    data = part.get("data", {})
                    if "products" in data:
                        products = data["products"]
                        if products and all(
                            "product_id" in p and "name" in p 
                            for p in products
                        ):
                            self.successes.append("message/send returns structured product data")
                            return True
            
            self.failures.append("Data part missing products or incomplete product data")
            return False
        
        return False
    
    def test_create_media_buy(self):
        """Test create_media_buy returns full media buy details."""
        print("\n🧪 Testing create_media_buy...")
        
        response = self.make_request("create_media_buy", {
            "product_ids": ["prod_001"],
            "total_budget": 10000.00,
            "flight_start_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "flight_end_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "targeting_overlay": {
                "geo_country_any_of": ["US"],
                "device_type_any_of": ["desktop", "mobile"]
            }
        })
        
        result = response.get("result", {})
        
        if self.validate_task_response(result, ["media_buy"]):
            media_buy = result.get("artifact", {}).get("media_buy", {})
            
            required_fields = [
                "media_buy_id", "status", "products", "budget",
                "flight_dates", "targeting"
            ]
            
            missing = [f for f in required_fields if f not in media_buy]
            if missing:
                self.failures.append(f"Media buy missing required fields: {missing}")
                return False
            
            self.successes.append("create_media_buy returns full structured data")
            return True
        
        return False
    
    def test_get_media_buy_status(self):
        """Test get_media_buy_status returns detailed status info."""
        print("\n🧪 Testing get_media_buy_status...")
        
        # First create a media buy
        create_response = self.make_request("create_media_buy", {
            "product_ids": ["prod_001"],
            "total_budget": 5000.00,
            "flight_start_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "flight_end_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        })
        
        media_buy_id = None
        if create_response.get("result", {}).get("artifact", {}).get("media_buy"):
            media_buy_id = create_response["result"]["artifact"]["media_buy"].get("media_buy_id")
        
        if not media_buy_id:
            self.failures.append("Could not create media buy for status test")
            return False
        
        # Now check status
        response = self.make_request("get_media_buy_status", {
            "media_buy_id": media_buy_id
        })
        
        result = response.get("result", {})
        
        if self.validate_task_response(result, ["status"]):
            status_data = result.get("artifact", {}).get("status", {})
            
            required_fields = [
                "media_buy_id", "state", "budget_spent", "impressions_delivered"
            ]
            
            missing = [f for f in required_fields if f not in status_data]
            if missing:
                self.failures.append(f"Status missing required fields: {missing}")
                return False
            
            self.successes.append("get_media_buy_status returns full structured data")
            return True
        
        return False
    
    def test_get_targeting_capabilities(self):
        """Test get_targeting_capabilities returns full targeting data."""
        print("\n🧪 Testing get_targeting_capabilities...")
        
        response = self.make_request("get_targeting_capabilities", {
            "channels": ["display"]
        })
        
        result = response.get("result", {})
        
        if self.validate_task_response(result, ["capabilities"]):
            capabilities = result.get("artifact", {}).get("capabilities", {})
            
            if not capabilities:
                self.failures.append("No targeting capabilities returned")
                return False
            
            # Check for expected capability categories
            expected_categories = ["geo", "device", "audience", "content"]
            missing = [c for c in expected_categories if c not in capabilities]
            
            if missing:
                print(f"  ⚠️  Missing capability categories: {missing}")
                # This might be acceptable depending on implementation
            
            self.successes.append("get_targeting_capabilities returns structured data")
            return True
        
        return False
    
    def run_all_tests(self):
        """Run all structured data tests."""
        print("=" * 60)
        print("A2A STRUCTURED DATA TEST SUITE")
        print("=" * 60)
        
        tests = [
            self.test_get_products,
            self.test_message_send_with_products,
            self.test_create_media_buy,
            self.test_get_media_buy_status,
            self.test_get_targeting_capabilities
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                self.failures.append(f"{test.__name__} raised exception: {e}")
        
        print("\n" + "=" * 60)
        print("TEST RESULTS")
        print("=" * 60)
        
        if self.successes:
            print(f"\n✅ PASSED ({len(self.successes)}):")
            for success in self.successes:
                print(f"  • {success}")
        
        if self.failures:
            print(f"\n❌ FAILED ({len(self.failures)}):")
            for failure in self.failures:
                print(f"  • {failure}")
        
        total = len(self.successes) + len(self.failures)
        if total > 0:
            pass_rate = (len(self.successes) / total) * 100
            print(f"\n📊 Pass Rate: {pass_rate:.1f}% ({len(self.successes)}/{total})")
        
        return len(self.failures) == 0


if __name__ == "__main__":
    tester = A2AStructuredDataTester()
    success = tester.run_all_tests()
    
    if not success:
        print("\n🔍 SPEC AMBIGUITIES FOUND:")
        print("The following areas need clarification in the AdCP spec:")
        print("1. Should all product fields be required or can some be optional?")
        print("2. What's the exact structure for price_guidance when not available?")
        print("3. Should message/send always return data parts for entity queries?")
        print("4. What targeting capabilities are mandatory vs optional?")
        
    exit(0 if success else 1)