import unittest
import os
import json

# Ensure the main module can be imported
from main import get_product_catalog
from schemas import ListProductsRequest, ListProductsResponse, Product
from database import init_db

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
