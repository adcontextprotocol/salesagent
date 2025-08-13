#!/usr/bin/env python3
"""
Direct test of the product validation fix by testing the DatabaseProductCatalog directly.
"""

import asyncio
import sys
import traceback
from product_catalog_providers.database import DatabaseProductCatalog
from db_config import get_db_connection


async def test_product_validation_direct():
    """Test the DatabaseProductCatalog directly to verify Pydantic validation fix."""
    
    print("Testing Product validation fix directly...")
    
    try:
        # Test the database product catalog directly
        catalog = DatabaseProductCatalog({})
        
        # Get products for test_publisher tenant
        products = await catalog.get_products(
            brief="test brief",
            tenant_id="test_publisher"
        )
        
        print(f"✅ SUCCESS: Got {len(products)} products without validation errors!")
        
        # Validate each product's structure
        for i, product in enumerate(products):
            print(f"\n--- Product {i+1}: {product.product_id} ---")
            print(f"✅ product_id: {product.product_id}")
            print(f"✅ name: {product.name}")
            print(f"✅ description: {product.description}")
            print(f"✅ is_custom: {product.is_custom}")
            print(f"✅ formats count: {len(product.formats)}")
            
            # Check each format
            for j, fmt in enumerate(product.formats):
                print(f"  Format {j+1}:")
                print(f"    ✅ format_id: {fmt.format_id}")
                print(f"    ✅ name: {fmt.name}")
                print(f"    ✅ description: {fmt.description}")
                print(f"    ✅ delivery_options: {fmt.delivery_options}")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        traceback.print_exc()
        return False


async def test_database_connection():
    """Test basic database connection and data structure."""
    
    print("\nTesting database connection...")
    
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT product_id, name, description, is_custom FROM products WHERE tenant_id = ?", ("test_publisher",))
        rows = cursor.fetchall()
        conn.close()
        
        print(f"✅ Database connection successful, found {len(rows)} products")
        
        for row in rows:
            product_data = {column: row[column] for column in row.keys()}
            print(f"  Raw data: {product_data}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🧪 Testing Product Validation Fix")
    print("=" * 50)
    
    # Test database connection first
    db_success = asyncio.run(test_database_connection())
    
    if db_success:
        # Test product validation
        validation_success = asyncio.run(test_product_validation_direct())
        
        if validation_success:
            print("\n🎉 All tests passed! The Pydantic validation fix is working.")
            sys.exit(0)
        else:
            print("\n💥 Product validation tests failed.")
            sys.exit(1)
    else:
        print("\n💥 Database connection failed.")
        sys.exit(1)