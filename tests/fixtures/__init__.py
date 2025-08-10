"""
Test fixtures for AdCP Sales Agent.

This module provides reusable test data and mock objects for testing.
"""

from .factories import *
from .mocks import *
from .builders import *

__all__ = [
    # Factories
    'TenantFactory',
    'PrincipalFactory',
    'ProductFactory',
    'MediaBuyFactory',
    'CreativeFactory',
    
    # Mocks
    'MockDatabase',
    'MockAdapter',
    'MockGeminiService',
    'MockOAuthProvider',
    
    # Builders
    'RequestBuilder',
    'ResponseBuilder',
    'TargetingBuilder',
    
    # Data loaders
    'load_fixture_data',
    'get_sample_creative',
    'get_sample_product',
]

import json
from pathlib import Path

def load_fixture_data(filename: str) -> dict:
    """Load JSON fixture data from the data directory."""
    fixture_path = Path(__file__).parent / "data" / filename
    with open(fixture_path) as f:
        return json.load(f)

def get_sample_creative(format_type: str = "display_300x250"):
    """Get a sample creative for testing."""
    return load_fixture_data("sample_creatives.json").get(format_type)

def get_sample_product(product_type: str = "run_of_site"):
    """Get a sample product for testing."""
    return load_fixture_data("sample_products.json").get(product_type)