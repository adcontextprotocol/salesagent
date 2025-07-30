"""
Product Catalog Provider System

This module provides a pluggable interface for product catalog retrieval.
Publishers can implement their own logic for matching products to briefs.
"""

from .base import ProductCatalogProvider
from .database import DatabaseProductCatalog
from .mcp import MCPProductCatalog
from .ai import AIProductCatalog

__all__ = [
    'ProductCatalogProvider',
    'DatabaseProductCatalog',
    'MCPProductCatalog',
    'AIProductCatalog',
]