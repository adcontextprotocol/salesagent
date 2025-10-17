"""Database-backed product catalog provider (current implementation)."""

import json
import logging
from typing import Any

from sqlalchemy.orm import joinedload

from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ProductModel
from src.core.database.product_pricing import get_product_pricing_options
from src.core.schemas import PriceGuidance, PricingModel, PricingOption, PricingParameters, Product

from .base import ProductCatalogProvider

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[Product]:
        """
        Get all products for the tenant from the database.

        Note: Currently ignores the brief and returns all products.
        Future enhancement could add brief-based filtering.
        """
        with get_db_session() as db_session:
            # Eager load pricing_options relationship to avoid N+1 queries
            # Use SQLAlchemy 2.0 select() pattern for consistency
            from sqlalchemy import select

            stmt = (
                select(ProductModel)
                .options(joinedload(ProductModel.pricing_options))
                .filter_by(tenant_id=tenant_id)
                .order_by(ProductModel.product_id)
            )
            # unique() must be called on execute result BEFORE scalars() with joinedload
            result = db_session.execute(stmt).unique()
            products = list(result.scalars().all())

            loaded_products = []
            for product_obj in products:
                # Get pricing options using helper (handles legacy fallback)
                pricing_options_data = get_product_pricing_options(product_obj)

                # Convert to Pydantic PricingOption objects
                # IMPORTANT: Always initialize to empty list, never None (Product schema expects list)
                pricing_options: list[PricingOption] = []
                if pricing_options_data:
                    try:
                        for po_dict in pricing_options_data:
                            # Generate pricing_option_id if not present
                            pricing_option_id = po_dict.get("pricing_option_id")
                            if not pricing_option_id:
                                # Generate from pricing model and currency
                                fixed_str = "fixed" if po_dict["is_fixed"] else "auction"
                                pricing_option_id = (
                                    f"{po_dict['pricing_model']}_{po_dict['currency'].lower()}_{fixed_str}"
                                )

                            pricing_options.append(
                                PricingOption(
                                    pricing_option_id=pricing_option_id,
                                    pricing_model=PricingModel(po_dict["pricing_model"]),
                                    rate=po_dict.get("rate"),
                                    currency=po_dict["currency"],
                                    is_fixed=po_dict["is_fixed"],
                                    price_guidance=(
                                        PriceGuidance(
                                            floor=po_dict["price_guidance"].get("floor", 0.0),
                                            p25=po_dict["price_guidance"].get("p25"),
                                            p50=po_dict["price_guidance"].get("p50"),
                                            p75=po_dict["price_guidance"].get("p75"),
                                            p90=po_dict["price_guidance"].get("p90"),
                                        )
                                        if po_dict.get("price_guidance")
                                        else None
                                    ),
                                    parameters=(
                                        PricingParameters(**po_dict["parameters"])
                                        if po_dict.get("parameters")
                                        else None
                                    ),
                                    min_spend_per_package=po_dict.get("min_spend_per_package"),
                                    supported=None,  # Populated dynamically by adapter
                                    unsupported_reason=None,
                                )
                            )
                    except Exception as e:
                        logger.warning(f"Failed to convert pricing options for product {product_obj.product_id}: {e}")
                        # Keep empty list on error - don't set to None

                # Convert ORM object to dictionary
                product_data = {
                    "product_id": product_obj.product_id,
                    "name": product_obj.name,
                    "description": product_obj.description,
                    "formats": product_obj.formats,
                    "pricing_options": pricing_options,
                    "delivery_type": product_obj.delivery_type,  # Required by AdCP spec
                    "is_custom": product_obj.is_custom,
                    "countries": product_obj.countries,
                    "properties": product_obj.properties if hasattr(product_obj, "properties") else None,
                    "property_tags": (
                        product_obj.property_tags
                        if hasattr(product_obj, "property_tags") and product_obj.property_tags
                        else ["all_inventory"]  # Default required per AdCP spec
                    ),
                }

                # Handle JSONB fields - PostgreSQL returns them as Python objects, SQLite as strings
                if product_data.get("formats"):
                    if isinstance(product_data["formats"], str):
                        product_data["formats"] = json.loads(product_data["formats"])

                # Note: Internal fields (targeting_template, implementation_config, countries)
                # are not included in product_data dict - they're not part of Product schema

                # Fix missing required fields for Pydantic validation

                # 1. Fix missing description (required field)
                if not product_data.get("description"):
                    product_data["description"] = f"Advertising product: {product_data.get('name', 'Unknown Product')}"

                # 2. Fix missing is_custom (should default to False)
                if product_data.get("is_custom") is None:
                    product_data["is_custom"] = False

                # 3. Keep formats as FormatId objects (dicts with agent_url and id)
                # Per AdCP v2.4 spec and Product schema: formats should be list[FormatId | FormatReference]
                # Database stores formats as list[dict] with {agent_url, id} structure
                # NO CONVERSION NEEDED - just pass through the format objects as-is
                if product_data.get("formats"):
                    logger.debug(
                        f"Formats for {product_data.get('product_id')}: {product_data['formats']} (keeping as FormatId objects)"
                    )

                # 4. Convert DECIMAL fields to float for Pydantic validation
                if product_data.get("min_spend") is not None:
                    logger.debug(
                        f"Original min_spend for {product_data.get('product_id')}: {product_data['min_spend']} (type: {type(product_data['min_spend'])})"
                    )
                    try:
                        product_data["min_spend"] = float(product_data["min_spend"])
                        logger.debug(f"Converted min_spend to float: {product_data['min_spend']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to convert min_spend to float: {e}, setting to None")
                        product_data["min_spend"] = None

                if product_data.get("cpm") is not None:
                    logger.debug(
                        f"Original cpm for {product_data.get('product_id')}: {product_data['cpm']} (type: {type(product_data['cpm'])})"
                    )
                    try:
                        product_data["cpm"] = float(product_data["cpm"])
                        logger.debug(f"Converted cpm to float: {product_data['cpm']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to convert cpm to float: {e}, setting to None")
                        product_data["cpm"] = None

                # Validate against AdCP protocol schema before returning
                try:
                    logger.debug(
                        f"About to validate product {product_data.get('product_id')}: price_guidance={product_data.get('price_guidance')} (type: {type(product_data.get('price_guidance'))})"
                    )
                    validated_product = Product(**product_data)
                    loaded_products.append(validated_product)
                    logger.debug(f"Successfully validated product {product_data.get('product_id')}")
                except Exception as e:
                    # CRITICAL: Product validation failures indicate data corruption or schema mismatch
                    # We MUST fail loudly, not silently skip products
                    error_msg = (
                        f"Product '{product_data.get('product_id')}' in database failed AdCP schema validation. "
                        f"This indicates data corruption or migration issue. Error: {e}"
                    )

                    # Log with full context for production debugging
                    logger.error(error_msg)
                    logger.error(f"Failed product data: {json.dumps(product_data, default=str)[:1000]}")

                    # Re-raise with context - don't silently skip products!
                    raise ValueError(error_msg) from e

            return loaded_products
