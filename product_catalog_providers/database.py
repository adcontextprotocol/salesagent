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
            product_data['formats'] = json.loads(product_data['formats'])
            # Remove targeting_template - it's internal and shouldn't be exposed
            product_data.pop('targeting_template', None)
            if product_data.get('price_guidance'):
                product_data['price_guidance'] = json.loads(product_data['price_guidance'])
            if product_data.get('implementation_config'):
                product_data['implementation_config'] = json.loads(product_data['implementation_config'])
            loaded_products.append(Product(**product_data))
        
        return loaded_products