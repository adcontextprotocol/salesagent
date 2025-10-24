"""
Shared test utilities for pricing model migration.

These helpers provide a consistent API for creating Products with pricing_options
across both integration/ and integration_v2/ test suites.
"""

from decimal import Decimal
from typing import Any

from src.core.database.models import PricingOption, Product


def create_test_product_with_pricing(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Test Product",
    pricing_model: str = "CPM",
    rate: Decimal | float | str = "15.00",
    is_fixed: bool = True,
    currency: str = "USD",
    min_spend_per_package: Decimal | float | str | None = None,
    formats: list[dict[str, str]] | None = None,
    targeting_template: dict | None = None,
    delivery_type: str = "guaranteed_impressions",
    property_tags: list[str] | None = None,
    **product_kwargs: Any,
) -> Product:
    """Create a Product with pricing_options using the new pricing model.

    This helper provides a simple API that mirrors the old Product(is_fixed_price=True, cpm=15.0)
    pattern but uses the new PricingOption table.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        pricing_model: One of: CPM, VCPM, CPC, FLAT_RATE, CPV, CPCV, CPP
        rate: Price rate (converted to Decimal)
        is_fixed: True for fixed pricing, False for auction
        currency: Currency code (default: USD)
        min_spend_per_package: Minimum spend per package (optional)
        formats: Creative formats (default: standard 300x250)
        targeting_template: Targeting template (default: empty)
        delivery_type: Delivery type (default: guaranteed_impressions)
        property_tags: Property tags (default: ["all_inventory"])
        **product_kwargs: Additional Product model fields

    Returns:
        Product instance with pricing_options populated

    Example:
        # Old pattern (BROKEN):
        product = Product(
            tenant_id="test",
            product_id="prod_1",
            is_fixed_price=True,
            cpm=15.0
        )

        # New pattern (WORKS):
        product = create_test_product_with_pricing(
            session,
            tenant_id="test",
            product_id="prod_1",
            pricing_model="CPM",
            rate=15.0,
            is_fixed=True
        )
    """
    import uuid

    # Auto-generate product_id if not provided
    if product_id is None:
        product_id = f"test_product_{uuid.uuid4().hex[:8]}"

    # Default formats (standard display ad)
    if formats is None:
        formats = [{"agent_url": "https://test.com", "id": "300x250"}]

    # Default targeting template
    if targeting_template is None:
        targeting_template = {}

    # Default property_tags (required by AdCP spec: must have properties OR property_tags)
    if property_tags is None and "properties" not in product_kwargs:
        property_tags = ["all_inventory"]

    # Convert rate to Decimal
    if isinstance(rate, str):
        rate_decimal = Decimal(rate)
    elif isinstance(rate, float):
        rate_decimal = Decimal(str(rate))
    else:
        rate_decimal = rate

    # Convert min_spend to Decimal if provided
    min_spend_decimal = None
    if min_spend_per_package is not None:
        if isinstance(min_spend_per_package, str):
            min_spend_decimal = Decimal(min_spend_per_package)
        elif isinstance(min_spend_per_package, float):
            min_spend_decimal = Decimal(str(min_spend_per_package))
        else:
            min_spend_decimal = min_spend_per_package

    # Create Product
    product = Product(
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        formats=formats,
        targeting_template=targeting_template,
        delivery_type=delivery_type,
        property_tags=property_tags,
        **product_kwargs,
    )
    session.add(product)
    session.flush()  # Get product into session before adding pricing_options

    # Create PricingOption
    pricing_option = PricingOption(
        tenant_id=tenant_id,
        product_id=product_id,
        pricing_model=pricing_model,
        rate=rate_decimal,
        currency=currency,
        is_fixed=is_fixed,
        min_spend_per_package=min_spend_decimal,
    )
    session.add(pricing_option)
    session.flush()  # Ensure pricing_option is persisted

    # Refresh product to load relationship
    session.refresh(product)

    return product


def create_auction_product(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Auction Product",
    pricing_model: str = "CPM",
    floor_cpm: Decimal | float | str = "1.00",
    currency: str = "USD",
    **kwargs: Any,
) -> Product:
    """Create a Product with auction pricing (is_fixed=False).

    Convenience wrapper for create_test_product_with_pricing with is_fixed=False.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        pricing_model: Pricing model (default: CPM)
        floor_cpm: Minimum floor price for auction
        currency: Currency code (default: USD)
        **kwargs: Additional arguments passed to create_test_product_with_pricing

    Returns:
        Product with auction pricing
    """
    return create_test_product_with_pricing(
        session=session,
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        pricing_model=pricing_model,
        rate=floor_cpm,
        is_fixed=False,
        currency=currency,
        **kwargs,
    )


def create_flat_rate_product(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Flat Rate Product",
    rate: Decimal | float | str = "10000.00",
    currency: str = "USD",
    **kwargs: Any,
) -> Product:
    """Create a Product with flat-rate pricing.

    Convenience wrapper for FLAT_RATE pricing model.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        rate: Total campaign cost
        currency: Currency code (default: USD)
        **kwargs: Additional arguments passed to create_test_product_with_pricing

    Returns:
        Product with flat-rate pricing
    """
    return create_test_product_with_pricing(
        session=session,
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        pricing_model="FLAT_RATE",
        rate=rate,
        is_fixed=True,
        currency=currency,
        delivery_type="sponsorship",  # FLAT_RATE typically uses sponsorship
        **kwargs,
    )
