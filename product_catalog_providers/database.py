"""Database-backed product catalog provider (current implementation)."""

import json
import logging
from typing import Any

from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ProductModel
from src.core.schemas import Product

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
            products = db_session.query(ProductModel).filter_by(tenant_id=tenant_id).all()

            loaded_products = []
            for product_obj in products:
                # Convert ORM object to dictionary
                product_data = {
                    "product_id": product_obj.product_id,
                    "name": product_obj.name,
                    "description": product_obj.description,
                    "formats": product_obj.formats,
                    "delivery_type": product_obj.delivery_type,
                    "is_fixed_price": product_obj.is_fixed_price,
                    "cpm": product_obj.cpm,
                    "price_guidance": product_obj.price_guidance,
                    "is_custom": product_obj.is_custom,
                    "countries": product_obj.countries,
                }

                # Handle JSONB fields - PostgreSQL returns them as Python objects, SQLite as strings
                if product_data.get("formats"):
                    if isinstance(product_data["formats"], str):
                        product_data["formats"] = json.loads(product_data["formats"])

                # Remove targeting_template - it's internal and shouldn't be exposed
                product_data.pop("targeting_template", None)

                if product_data.get("price_guidance"):
                    logger.debug(
                        f"Processing price_guidance for {product_data.get('product_id')}: {product_data['price_guidance']} (type: {type(product_data['price_guidance'])})"
                    )
                    if isinstance(product_data["price_guidance"], str):
                        product_data["price_guidance"] = json.loads(product_data["price_guidance"])
                        logger.debug(f"Parsed price_guidance: {product_data['price_guidance']}")

                    # Fix price_guidance structure - convert min/max to floor/percentiles
                    if isinstance(product_data["price_guidance"], dict):
                        pg = product_data["price_guidance"]
                        # Handle both "min"/"max" and "min_spend"/"max_spend" formats
                        if "min" in pg or "max" in pg or "min_spend" in pg or "max_spend" in pg:
                            # Convert min/max to floor and percentiles
                            min_val = pg.get("min", pg.get("min_spend", pg.get("floor", 0)))
                            max_val = pg.get("max", pg.get("max_spend", 10))
                            fixed_price_guidance = {
                                "floor": min_val,
                                "p50": (min_val + max_val) / 2,  # Median as midpoint
                                "p90": max_val * 0.9,  # 90th percentile
                            }
                            product_data["price_guidance"] = fixed_price_guidance
                            logger.debug(f"Fixed price_guidance structure: {fixed_price_guidance}")

                # Remove implementation_config - it's internal and should NEVER be exposed to buyers
                # This contains proprietary ad server configuration details
                product_data.pop("implementation_config", None)

                # Fix missing required fields for Pydantic validation

                # 1. Fix missing description (required field)
                if not product_data.get("description"):
                    product_data["description"] = f"Advertising product: {product_data.get('name', 'Unknown Product')}"

                # 2. Fix missing is_custom (should default to False)
                if product_data.get("is_custom") is None:
                    product_data["is_custom"] = False

                # 3. Fix incomplete format objects
                if product_data.get("formats"):
                    fixed_formats = []
                    for format_obj in product_data["formats"]:
                        # Handle case where format_obj might be a string instead of dict
                        if isinstance(format_obj, str):
                            # Check if it's a JSON string first
                            try:
                                parsed = json.loads(format_obj)
                                if isinstance(parsed, dict):
                                    format_obj = parsed
                                else:
                                    # It's just a format identifier string like "display_300x250"
                                    # Convert to proper format object
                                    format_parts = format_obj.split("_")
                                    if len(format_parts) >= 2:
                                        format_type = format_parts[0]  # e.g., "display"
                                        dimensions = "_".join(format_parts[1:])  # e.g., "300x250"
                                    else:
                                        format_type = "unknown"
                                        dimensions = format_obj

                                    format_obj = {
                                        "format_id": format_obj,  # Use the string as the format_id
                                        "name": format_obj,
                                        "type": format_type,
                                        "description": f"{format_type.title()} {dimensions} format",
                                        "delivery_options": {
                                            "hosted": None,
                                            "vast": None if format_type != "video" else {"required": False},
                                        },
                                    }
                            except (json.JSONDecodeError, TypeError):
                                # It's a plain string format identifier
                                format_parts = format_obj.split("_")
                                if len(format_parts) >= 2:
                                    format_type = format_parts[0]  # e.g., "display"
                                    dimensions = "_".join(format_parts[1:])  # e.g., "300x250"
                                else:
                                    format_type = "unknown"
                                    dimensions = format_obj

                                format_obj = {
                                    "format_id": format_obj,  # Use the string as the format_id
                                    "name": format_obj,
                                    "type": format_type,
                                    "description": f"{format_type.title()} {dimensions} format",
                                    "delivery_options": {
                                        "hosted": None,
                                        "vast": None if format_type != "video" else {"required": False},
                                    },
                                }

                        # Ensure we have a dictionary
                        if not isinstance(format_obj, dict):
                            logger.warning(f"Skipping non-dict format after conversion: {format_obj}")
                            continue

                        # Ensure format has required format_id field
                        if not format_obj.get("format_id"):
                            format_obj["format_id"] = format_obj.get("name", "unknown_format")

                        # Ensure format has required description field
                        if not format_obj.get("description"):
                            format_obj["description"] = (
                                f"{format_obj.get('name', 'Unknown Format')} - {format_obj.get('type', 'unknown')} format"
                            )

                        # Ensure format has required delivery_options field
                        if not format_obj.get("delivery_options"):
                            format_obj["delivery_options"] = {"hosted": None, "vast": None}

                        fixed_formats.append(format_obj)
                    product_data["formats"] = fixed_formats

                # Validate against AdCP protocol schema before returning
                try:
                    logger.debug(
                        f"About to validate product {product_data.get('product_id')}: price_guidance={product_data.get('price_guidance')} (type: {type(product_data.get('price_guidance'))})"
                    )
                    validated_product = Product(**product_data)
                    loaded_products.append(validated_product)
                    logger.debug(f"Successfully validated product {product_data.get('product_id')}")
                except Exception as e:
                    logger.error(f"Product {product_data.get('product_id')} failed validation: {e}")
                    logger.debug(f"Product data that failed: {product_data}")
                    # Skip invalid products rather than failing entire request
                    continue

            return loaded_products
