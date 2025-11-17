"""Product conversion utilities.

This module provides functions to convert between database Product models
and AdCP Product schema objects, including proper handling of pricing options,
publisher properties, and all required fields.
"""

from adcp.types.generated_poc.product import Product


def convert_pricing_option_to_adcp(pricing_option) -> dict:
    """Convert database PricingOption to AdCP pricing option discriminated union.

    Args:
        pricing_option: Database PricingOption model

    Returns:
        Dict representing AdCP pricing option (CpmFixedRatePricingOption, etc.)
    """
    # Base fields common to all pricing options
    result = {
        "pricing_model": pricing_option.pricing_model.lower(),
        "currency": pricing_option.currency,
        "pricing_option_id": f"{pricing_option.pricing_model.lower()}_{pricing_option.currency.lower()}_{'fixed' if pricing_option.is_fixed else 'auction'}",
    }

    # Add min_spend_per_package if present
    if pricing_option.min_spend_per_package:
        result["min_spend_per_package"] = float(pricing_option.min_spend_per_package)

    # Handle fixed vs auction pricing
    if pricing_option.is_fixed and pricing_option.rate:
        # Fixed rate pricing
        result["rate"] = float(pricing_option.rate)
    elif not pricing_option.is_fixed and pricing_option.price_guidance:
        # Auction pricing with price guidance
        result["price_guidance"] = pricing_option.price_guidance

    # Add pricing model-specific parameters
    # CPP and some other pricing models need parameters as a nested object
    if pricing_option.parameters:
        pricing_model = pricing_option.pricing_model.lower()
        if pricing_model in ("cpp", "cpcv", "cpv"):
            # These models expect parameters as a nested object
            result["parameters"] = pricing_option.parameters
        else:
            # Other models may use parameters differently
            result.update(pricing_option.parameters)

    return result


def convert_product_model_to_schema(product_model) -> Product:
    """Convert database Product model to Product schema.

    Args:
        product_model: Product database model

    Returns:
        Product schema object
    """
    # Map fields from model to schema
    product_data = {}

    # Required fields per AdCP spec
    product_data["product_id"] = product_model.product_id
    product_data["name"] = product_model.name
    product_data["description"] = product_model.description
    product_data["delivery_type"] = product_model.delivery_type

    # format_ids: Use effective_format_ids which auto-resolves from profile if set
    product_data["format_ids"] = product_model.effective_format_ids or []

    # publisher_properties: Use effective_properties which returns AdCP 2.0.0 discriminated union format
    effective_props = product_model.effective_properties
    if not effective_props:
        raise ValueError(
            f"Product {product_model.product_id} has no publisher_properties. "
            "All products must have at least one property per AdCP spec."
        )
    product_data["publisher_properties"] = effective_props

    # delivery_measurement: Provide default if missing (required per AdCP spec)
    if product_model.delivery_measurement:
        product_data["delivery_measurement"] = product_model.delivery_measurement
    else:
        # Default measurement provider
        product_data["delivery_measurement"] = {
            "provider": "publisher",
            "notes": "Measurement methodology not specified",
        }

    # pricing_options: Convert database PricingOption models to AdCP discriminated unions
    if product_model.pricing_options:
        product_data["pricing_options"] = [convert_pricing_option_to_adcp(po) for po in product_model.pricing_options]
    else:
        product_data["pricing_options"] = []

    # Optional fields
    if product_model.measurement:
        product_data["measurement"] = product_model.measurement
    if product_model.creative_policy:
        product_data["creative_policy"] = product_model.creative_policy
    # Note: price_guidance is database metadata, not in AdCP Product schema - omit it
    # Pricing information should be in pricing_options per AdCP spec
    # Note: countries is NOT in AdCP Product schema - omit it
    # if product_model.countries:
    #     product_data["countries"] = product_model.countries
    if product_model.product_card:
        product_data["product_card"] = product_model.product_card
    if product_model.product_card_detailed:
        product_data["product_card_detailed"] = product_model.product_card_detailed
    if product_model.placements:
        product_data["placements"] = product_model.placements
    if product_model.reporting_capabilities:
        product_data["reporting_capabilities"] = product_model.reporting_capabilities

    # Default is_custom to False if not set
    product_data["is_custom"] = product_model.is_custom if product_model.is_custom else False

    return Product(**product_data)
