"""Helper functions for working with generated schemas.

This module provides convenience functions for constructing complex generated schemas
without losing type safety. Unlike adapters (which wrap schemas in dict[str, Any]),
these helpers work directly with the generated Pydantic models.

Philosophy:
- Generated schemas are the source of truth (always in sync with AdCP spec)
- Helpers make construction easier without sacrificing type safety
- Custom logic (validators, conversions) lives here, not in wrapper classes
"""

from typing import Any

from adcp import GetProductsRequest, GetProductsResponse, Product
from adcp.types.generated_poc.core.brand_manifest import BrandManifest
from adcp.types.generated_poc.core.context import ContextObject
from adcp.types.generated_poc.core.product_filters import ProductFilters


def to_context_object(context: dict[str, Any] | ContextObject | None) -> ContextObject | None:
    """Convert dict context to ContextObject for adcp 2.12.0+ compatibility.

    Args:
        context: Context as dict or ContextObject or None

    Returns:
        ContextObject or None
    """
    if context is None:
        return None
    if isinstance(context, ContextObject):
        return context
    if isinstance(context, dict):
        return ContextObject(**context)
    return None  # Fallback for unexpected types


def create_get_products_request(
    brief: str = "",
    brand_manifest: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> GetProductsRequest:
    """Create GetProductsRequest aligned with adcp v1.2.1 spec.

    Args:
        brief: Natural language description of campaign requirements
        brand_manifest: Brand information as dict. Must follow AdCP BrandManifest schema.
                       Example: {"name": "Acme", "url": "https://acme.com"}
                       Or: {"url": "https://acme.com"}
        filters: Structured filters for product discovery

    Returns:
        GetProductsRequest

    Examples:
        >>> req = create_get_products_request(
        ...     brand_manifest={"name": "Acme", "url": "https://acme.com"},
        ...     brief="Display ads"
        ... )
    """
    # Adapt brand_manifest to ensure 'name' field exists (adcp 2.5.0 requirement)
    brand_manifest_adapted = brand_manifest
    if brand_manifest and isinstance(brand_manifest, dict):
        if "name" not in brand_manifest:
            # If only 'url' provided, use domain as name
            if "url" in brand_manifest:
                from urllib.parse import urlparse

                url_str = brand_manifest["url"]
                domain = urlparse(url_str).netloc or url_str
                brand_manifest_adapted = {**brand_manifest, "name": domain}
            else:
                # Fallback: use a placeholder name
                brand_manifest_adapted = {**brand_manifest, "name": "Brand"}

    # Create GetProductsRequest with proper types
    # Convert dict inputs to proper Pydantic models
    brand_manifest_obj = BrandManifest(**brand_manifest_adapted) if brand_manifest_adapted else None
    filters_obj = ProductFilters(**filters) if filters else None

    return GetProductsRequest(
        brand_manifest=brand_manifest_obj,
        brief=brief or None,
        filters=filters_obj,
        context=to_context_object(context),
    )


def create_get_products_response(
    products: list[Product | dict[str, Any]],
    errors: list | None = None,
    request_context: dict[str, Any] | None = None,
) -> GetProductsResponse:
    """Create GetProductsResponse.

    Note: The generated GetProductsResponse is already a simple BaseModel,
    so this helper mainly just provides defaults and type conversion.

    Args:
        products: List of matching products (Product objects or dicts)
        errors: List of errors (if any)

    Returns:
        GetProductsResponse
    """
    # Convert dict products to Product objects
    product_list: list[Product] = []
    for p in products:
        if isinstance(p, dict):
            product_list.append(Product(**p))
        else:
            product_list.append(p)

    return GetProductsResponse(
        products=product_list,
        errors=errors,
        context=to_context_object(request_context),
    )


# Re-export commonly used generated types for convenience
__all__ = [
    "to_context_object",
    "create_get_products_request",
    "create_get_products_response",
    # Re-export types for type hints
    "GetProductsRequest",
    "GetProductsResponse",
    "Product",
    "ContextObject",
]
