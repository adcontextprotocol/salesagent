#!/usr/bin/env python3
"""Basic tests for AI product features that don't require external dependencies."""

import pytest
import json
import tempfile
import sqlite3
from datetime import datetime

# Test only the modules that don't require heavy dependencies
from default_products import get_default_products, create_default_products_for_tenant, get_industry_specific_products


class TestDefaultProducts:
    """Test default product functionality."""
    
    def test_get_default_products(self):
        """Test that default products are returned correctly."""
        products = get_default_products()
        
        assert len(products) == 6
        assert all('product_id' in p for p in products)
        assert all('name' in p for p in products)
        assert all('formats' in p for p in products)
        
        # Check specific products exist
        product_ids = [p['product_id'] for p in products]
        assert 'run_of_site_display' in product_ids
        assert 'homepage_takeover' in product_ids
        assert 'mobile_interstitial' in product_ids
        assert 'video_preroll' in product_ids
        assert 'native_infeed' in product_ids
        assert 'contextual_display' in product_ids
        
        # Verify structure
        for product in products:
            assert 'delivery_type' in product
            assert product['delivery_type'] in ['guaranteed', 'non_guaranteed']
            
            if product['delivery_type'] == 'guaranteed':
                assert 'cpm' in product and product['cpm'] is not None
            else:
                assert 'price_guidance' in product
                assert 'min' in product['price_guidance']
                assert 'max' in product['price_guidance']
    
    def test_industry_specific_products(self):
        """Test industry-specific product templates."""
        # Test each industry
        industries = ['news', 'sports', 'entertainment', 'ecommerce']
        
        for industry in industries:
            products = get_industry_specific_products(industry)
            assert len(products) > 0
            
            # Should include standard products plus industry-specific
            standard_ids = {p['product_id'] for p in get_default_products()}
            industry_ids = {p['product_id'] for p in products}
            
            # Should have at least one industry-specific product
            industry_specific = industry_ids - standard_ids
            assert len(industry_specific) > 0, f"No industry-specific products for {industry}"
            
            # Verify industry-specific products are well-formed
            for product_id in industry_specific:
                product = next(p for p in products if p['product_id'] == product_id)
                assert 'name' in product
                assert 'description' in product
                assert 'formats' in product
                assert len(product['formats']) > 0
    
    def test_create_default_products_for_tenant(self):
        """Test creating default products in database."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            conn = sqlite3.connect(tmp.name)
            
            # Create products table with composite primary key
            conn.execute("""
                CREATE TABLE products (
                    product_id TEXT,
                    tenant_id TEXT,
                    name TEXT,
                    description TEXT,
                    creative_formats TEXT,
                    delivery_type TEXT,
                    cpm REAL,
                    price_guidance_min REAL,
                    price_guidance_max REAL,
                    countries TEXT,
                    targeting_template TEXT,
                    implementation_config TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (tenant_id, product_id)
                )
            """)
            
            # Create products for default industry
            created = create_default_products_for_tenant(conn, 'test_tenant')
            assert len(created) == 6
            
            # Verify products were created
            cursor = conn.execute("SELECT COUNT(*) FROM products WHERE tenant_id = ?", ('test_tenant',))
            count = cursor.fetchone()[0]
            assert count == 6
            
            # Verify product details
            cursor = conn.execute("""
                SELECT product_id, name, delivery_type, cpm, price_guidance_min, price_guidance_max 
                FROM products WHERE tenant_id = ?
            """, ('test_tenant',))
            
            products = cursor.fetchall()
            for product in products:
                product_id, name, delivery_type, cpm, price_min, price_max = product
                assert product_id is not None
                assert name is not None
                assert delivery_type in ['guaranteed', 'non_guaranteed']
                
                if delivery_type == 'guaranteed':
                    assert cpm is not None and cpm > 0
                else:
                    assert price_min is not None and price_max is not None
                    assert price_min < price_max
            
            # Test idempotency - running again should create 0
            created_again = create_default_products_for_tenant(conn, 'test_tenant')
            assert len(created_again) == 0
            
            # Test with industry - news industry has 1 unique product + 6 defaults = 7 total
            created_industry = create_default_products_for_tenant(conn, 'test_tenant_2', 'news')
            assert len(created_industry) == 7  # 6 defaults + 1 news-specific
            
            conn.close()


class TestProductTemplates:
    """Test product template functionality."""
    
    def test_template_completeness(self):
        """Ensure all templates have required fields."""
        all_templates = get_default_products()
        
        # Add all industry templates
        for industry in ['news', 'sports', 'entertainment', 'ecommerce']:
            templates = get_industry_specific_products(industry)
            # Only add non-default templates
            default_ids = {t['product_id'] for t in all_templates}
            for template in templates:
                if template['product_id'] not in default_ids:
                    all_templates.append(template)
        
        for template in all_templates:
            # Required fields
            assert 'product_id' in template
            assert 'name' in template
            assert 'description' in template
            assert 'formats' in template
            assert 'delivery_type' in template
            
            # Validate formats
            assert isinstance(template['formats'], list)
            assert len(template['formats']) > 0
            
            # Validate pricing
            if template['delivery_type'] == 'guaranteed':
                assert 'cpm' in template
                assert template['cpm'] > 0
            else:
                assert 'price_guidance' in template
                assert 'min' in template['price_guidance']
                assert 'max' in template['price_guidance']
                assert template['price_guidance']['min'] <= template['price_guidance']['max']
            
            # Optional but recommended fields
            if 'targeting_template' in template:
                assert isinstance(template['targeting_template'], dict)
            
            if 'countries' in template:
                assert isinstance(template['countries'], list) or template['countries'] is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])