"""Factory for creating product catalog providers based on configuration."""

from typing import Any

from .ai import AIProductCatalog
from .base import ProductCatalogProvider
from .database import DatabaseProductCatalog
from .mcp import MCPProductCatalog

# Registry of available providers
PROVIDER_REGISTRY = {
    "database": DatabaseProductCatalog,
    "mcp": MCPProductCatalog,
    "ai": AIProductCatalog,
}

# Cache for provider instances (one per tenant)
_provider_cache: dict[str, ProductCatalogProvider] = {}


async def get_product_catalog_provider(tenant_id: str, tenant_config: dict[str, Any]) -> ProductCatalogProvider:
    """
    Get or create a product catalog provider for a tenant.

    The provider type and configuration are determined by the tenant's
    product_catalog configuration:

    Example tenant config:
    {
        "product_catalog": {
            "provider": "ai",  # or "database", "mcp"
            "config": {
                # Provider-specific configuration
                "model": "gemini-1.5-flash",
                "max_products": 5
            }
        }
    }

    If no product_catalog config is present, defaults to database provider.
    """
    # Check cache first
    if tenant_id in _provider_cache:
        return _provider_cache[tenant_id]

    # Get product catalog configuration
    catalog_config = tenant_config.get("product_catalog", {})
    provider_type = catalog_config.get("provider", "database")
    provider_config = catalog_config.get("config", {})

    # Validate provider type
    if provider_type not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown product catalog provider: {provider_type}")

    # Create provider instance
    provider_class = PROVIDER_REGISTRY[provider_type]
    provider = provider_class(provider_config)

    # Initialize if needed
    await provider.initialize()

    # Cache for future use
    _provider_cache[tenant_id] = provider

    return provider


async def cleanup_providers():
    """Clean up all cached providers (call on shutdown)."""
    for provider in _provider_cache.values():
        await provider.shutdown()
    _provider_cache.clear()


def register_provider(name: str, provider_class: type):
    """
    Register a custom product catalog provider.

    This allows external code to add new provider types:

    ```python
    from product_catalog_providers import register_provider

    class MyCustomProvider(ProductCatalogProvider):
        # ... implementation ...

    register_provider('custom', MyCustomProvider)
    ```
    """
    if not issubclass(provider_class, ProductCatalogProvider):
        raise ValueError(f"{provider_class} must inherit from ProductCatalogProvider")

    PROVIDER_REGISTRY[name] = provider_class
