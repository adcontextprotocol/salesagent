import unittest
import os
import json

# Ensure the main module can be imported
from main import get_product_catalog
from schemas import ListProductsRequest, ListProductsResponse, Product
from database import init_db
from config_loader import set_current_tenant, get_default_tenant
from db_config import get_db_connection
import uuid

class TestAdcpServerV2_3(unittest.TestCase):
    """
    Tests for the V2.3 AdCP Buy-Side Server.
    Focuses on schema conformance for AI-driven tools.
    """

    @classmethod
    def setUpClass(cls):
        """Set up the database once for all tests for the V2.3 spec."""
        db_file = "adcp.db"
        if os.path.exists(db_file):
            os.remove(db_file)
        init_db()
        
        # Create a test tenant and set it as current
        conn = get_db_connection()
        try:
            tenant_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO tenants (tenant_id, name, subdomain, config, billing_plan, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                tenant_id,
                "Test Tenant",
                f"test_{tenant_id[:8]}",
                json.dumps({
                    "adapters": {"mock": {"enabled": True}},
                    "features": {"max_daily_budget": 10000},
                    "creative_engine": {"auto_approve_formats": ["display_300x250", "display_728x90"]}
                }),
                "test"
            ))
            
            # Create test products
            products_data = [
                ("prod_1", "Display Banner Package", "Premium display advertising", json.dumps(["display_300x250", "display_728x90"]), "guaranteed", True, 5.0, json.dumps({"floor": 5.0, "p50": 7.5, "p90": 10.0})),
                ("prod_2", "Video Pre-Roll", "High-impact video ads", json.dumps(["video_instream"]), "non_guaranteed", False, 15.0, json.dumps({"floor": 12.0, "p50": 16.0, "p90": 20.0})),
                ("prod_3", "Native Content Package", "Native advertising", json.dumps(["native_content"]), "guaranteed", True, 8.0, json.dumps({"floor": 6.0, "p50": 9.0, "p90": 12.0}))
            ]
            
            for prod_data in products_data:
                conn.execute("""
                    INSERT INTO products (product_id, tenant_id, name, description, formats, delivery_type, 
                                       is_fixed_price, cpm, price_guidance, countries, targeting_template)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (prod_data[0], tenant_id, prod_data[1], prod_data[2], prod_data[3], prod_data[4], 
                      prod_data[5], prod_data[6], prod_data[7], json.dumps({"countries": ["US", "CA"]}), json.dumps({})))
            
            conn.connection.commit()
            
            # Set the tenant in context
            set_current_tenant({
                'tenant_id': tenant_id,
                'name': 'Test Tenant',
                'subdomain': f"test_{tenant_id[:8]}",
                'config': {
                    "adapters": {"mock": {"enabled": True}},
                    "features": {"max_daily_budget": 10000},
                    "creative_engine": {"auto_approve_formats": ["display_300x250", "display_728x90"]}
                }
            })
        finally:
            conn.close()
        
        # Load the full product catalog once for all tests
        cls.product_catalog = get_product_catalog()
        cls.product_catalog_ids = {p.product_id for p in cls.product_catalog}


    def test_product_catalog_schema_conformance(self):
        """
        Tests that the product catalog properly validates against schemas.
        Since list_products now requires authentication context, we test
        the underlying catalog functionality instead.
        """
        # Get the product catalog
        products = get_product_catalog()
        
        # 1. Primary Assertion: The catalog must not be empty
        self.assertIsInstance(products, list)
        self.assertGreater(len(products), 0, "Product catalog should not be empty")
        
        # 2. Secondary Assertion: All products must be valid Product instances
        for product in products:
            self.assertIsInstance(product, Product)
            # Verify required fields
            self.assertTrue(hasattr(product, 'product_id'))
            self.assertTrue(hasattr(product, 'name'))
            self.assertTrue(hasattr(product, 'description'))
            self.assertTrue(hasattr(product, 'formats'))
            self.assertTrue(hasattr(product, 'delivery_type'))
            
        # 3. Tertiary Assertion: Create a mock response to test schema validation
        response = ListProductsResponse(products=products[:2])  # Test with first 2 products
        self.assertIsInstance(response, ListProductsResponse)
        self.assertEqual(len(response.products), 2)

if __name__ == '__main__':
    unittest.main()
