"""Database-backed product catalog provider (current implementation)."""

import json
from typing import List, Dict, Any, Optional
from .base import ProductCatalogProvider
from schemas import Product
from db_config import get_db_connection


class DatabaseProductCatalog(ProductCatalogProvider):
    """
    Simple database-backed product catalog.
    Returns all products from the database without filtering by brief.
    
    This maintains backward compatibility with the current implementation.
    """
    
    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        principal_data: Optional[Dict[str, Any]] = None
    ) -> List[Product]:
        """
        Get all products for the tenant from the database.
        
        Note: Currently ignores the brief and returns all products.
        Future enhancement could add brief-based filtering.
        """
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT * FROM products WHERE tenant_id = ?",
            (tenant_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        loaded_products = []
        for row in rows:
            # Convert Row object to dictionary
            product_data = {column: row[column] for column in row.keys()}
            # Remove tenant_id as it's not in the Product schema
            product_data.pop('tenant_id', None)
            
            # Handle JSONB fields - PostgreSQL returns them as Python objects, SQLite as strings
            if product_data.get('formats'):
                if isinstance(product_data['formats'], str):
                    product_data['formats'] = json.loads(product_data['formats'])
            
            # Remove targeting_template - it's internal and shouldn't be exposed
            product_data.pop('targeting_template', None)
            
            if product_data.get('price_guidance'):
                if isinstance(product_data['price_guidance'], str):
                    product_data['price_guidance'] = json.loads(product_data['price_guidance'])
            
            # Remove implementation_config - it's internal and should NEVER be exposed to buyers
            # This contains proprietary ad server configuration details
            product_data.pop('implementation_config', None)
            
            # Fix missing required fields for Pydantic validation
            
            # 1. Fix missing description (required field)
            if not product_data.get('description'):
                product_data['description'] = f"Advertising product: {product_data.get('name', 'Unknown Product')}"
            
            # 2. Fix missing is_custom (should default to False)
            if product_data.get('is_custom') is None:
                product_data['is_custom'] = False
            
            # 3. Fix incomplete format objects
            if product_data.get('formats'):
                fixed_formats = []
                for format_obj in product_data['formats']:
                    # Ensure format has required description field
                    if not format_obj.get('description'):
                        format_obj['description'] = f"{format_obj.get('name', 'Unknown Format')} - {format_obj.get('type', 'unknown')} format"
                    
                    # Ensure format has required delivery_options field
                    if not format_obj.get('delivery_options'):
                        format_obj['delivery_options'] = {
                            "hosted": None,
                            "vast": None
                        }
                    
                    fixed_formats.append(format_obj)
                product_data['formats'] = fixed_formats
            
            loaded_products.append(Product(**product_data))
        
        return loaded_products