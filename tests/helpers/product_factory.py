"""Test helper for creating AdCP-compliant Product objects.

This module provides factory functions for creating Product objects that comply
with the AdCP spec, including all required fields. Use these in tests instead of
manually constructing Product objects to avoid validation errors.
"""

from typing import Any

from adcp import FormatId, Product


def create_test_product(
    product_id: str = "test_product",
    name: str = "Test Product",
    description: str = "Test product description",
    format_ids: list[str | dict] | None = None,
    publisher_properties: list[dict[str, Any]] | None = None,
    delivery_type: str = "guaranteed",
    pricing_options: list[dict[str, Any]] | None = None,
    delivery_measurement: dict[str, Any] | None = None,
    **kwargs,
) -> Product:
    """Create a test Product with all required fields.

    Args:
        product_id: Product identifier
        name: Product name
        description: Product description
        format_ids: List of format IDs (as strings or dicts). Defaults to ["display_300x250"]
        publisher_properties: List of property objects. Defaults to minimal test property
        delivery_type: "guaranteed" or "non_guaranteed"
        pricing_options: List of pricing option dicts. Defaults to minimal CPM option
        delivery_measurement: Delivery measurement dict. Defaults to test provider
        **kwargs: Additional optional fields (measurement, creative_policy, etc.)

    Returns:
        AdCP-compliant Product object

    Example:
        # Minimal product
        product = create_test_product()

        # Custom product
        product = create_test_product(
            product_id="video_premium",
            format_ids=["video_1920x1080"],
            pricing_options=[{
                "pricing_model": "cpm",
                "currency": "USD",
            }]
        )
    """
    # Default format_ids if not provided
    if format_ids is None:
        format_ids = ["display_300x250"]

    # Convert format_ids to FormatId objects
    format_id_objects = []
    for fmt in format_ids:
        if isinstance(fmt, str):
            # String format ID - convert to FormatId object
            format_id_objects.append(FormatId(agent_url="https://creative.adcontextprotocol.org", id=fmt))
        elif isinstance(fmt, dict):
            # Dict with agent_url and id
            format_id_objects.append(FormatId(**fmt))
        else:
            # Already a FormatId object
            format_id_objects.append(fmt)

    # Default publisher_properties if not provided
    if publisher_properties is None:
        publisher_properties = [
            {
                "publisher_domain": "test.example.com",
                "property_id": "test_property_1",
                "property_name": "Test Property",
                "property_type": "website",
            }
        ]

    # Default delivery_measurement if not provided
    if delivery_measurement is None:
        delivery_measurement = {
            "provider": "test_provider",
            "notes": "Test measurement methodology",
        }

    # Default pricing_options if not provided (empty list is valid for anonymous users)
    if pricing_options is None:
        pricing_options = [
            {
                "pricing_model": "cpm",
                "currency": "USD",
            }
        ]

    return Product(
        product_id=product_id,
        name=name,
        description=description,
        publisher_properties=publisher_properties,
        format_ids=format_id_objects,
        delivery_type=delivery_type,
        pricing_options=pricing_options,
        delivery_measurement=delivery_measurement,
        **kwargs,
    )


def create_minimal_product(**overrides) -> Product:
    """Create a product with absolute minimal required fields.

    Useful for testing required field validation.

    Args:
        **overrides: Override any default values

    Returns:
        Product with minimal required fields
    """
    defaults = {
        "product_id": "minimal",
        "name": "Minimal",
        "description": "Minimal test product",
        "publisher_properties": [
            {"publisher_domain": "test.com", "property_id": "p1", "property_name": "Test", "property_type": "website"}
        ],
        "format_ids": [FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")],
        "delivery_type": "guaranteed",
        "pricing_options": [{"pricing_model": "cpm", "currency": "USD"}],
        "delivery_measurement": {"provider": "test", "notes": "Test"},
    }
    defaults.update(overrides)
    return Product(**defaults)


def create_product_with_empty_pricing(**overrides) -> Product:
    """Create a product with empty pricing_options (anonymous user case).

    Args:
        **overrides: Override any default values

    Returns:
        Product with empty pricing_options list
    """
    return create_test_product(pricing_options=[], **overrides)
