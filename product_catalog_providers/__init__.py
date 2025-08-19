"""
Product Catalog Provider System

This module provides a pluggable interface for product catalog retrieval.
Publishers can implement their own logic for matching products to briefs.
"""

from .ai import AIProductCatalog
from .base import ProductCatalogProvider
from .database import DatabaseProductCatalog
from .mcp import MCPProductCatalog

__all__ = [
    "ProductCatalogProvider",
    "DatabaseProductCatalog",
    "MCPProductCatalog",
    "AIProductCatalog",
]
