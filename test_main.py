import unittest
import os
import json

# Ensure the main module can be imported
from main import list_products, get_product_catalog
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


    def test_list_products_schema_conformance(self):
        """
        Tests that the AI-driven list_products tool returns a response that
        successfully validates against the ListProductsResponse Pydantic model.
        This is the most critical test for ensuring reliable AI output.
        """
        # Use the same brief as the simulation for consistency
        with open('brief.json', 'r') as f:
            brief_data = json.load(f)
        
        request = ListProductsRequest(brief=brief_data['brief'])

        try:
            # Directly call the tool's function
            response = list_products.fn(request=request)
            
            # 1. Primary Assertion: The response must be a valid ListProductsResponse object.
            # Pydantic will raise a ValidationError if the JSON from the AI does not
            # match the schema, causing the test to fail as intended.
            self.assertIsInstance(response, ListProductsResponse)

            # 2. Secondary Assertion: The response should not be empty.
            self.assertIsInstance(response.products, list)
            self.assertGreater(len(response.products), 0, "The AI should have recommended at least one product.")

            # 3. Tertiary Assertion: Every product in the response must exist in the original catalog.
            # This verifies the AI followed the instruction to not invent products.
            for product in response.products:
                self.assertIsInstance(product, Product)
                self.assertIn(product.product_id, self.product_catalog_ids,
                              f"AI returned a product_id '{product.product_id}' that does not exist in the catalog.")

        except Exception as e:
            self.fail(f"list_products.fn raised an unexpected exception: {e}")

if __name__ == '__main__':
    unittest.main()
