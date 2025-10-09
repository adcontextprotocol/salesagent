"""Format resolution with tenant custom formats and product overrides.

Provides layered format lookup:
1. Product-level overrides (from product.implementation_config.format_overrides)
2. Tenant-level custom formats (from creative_formats database table)
3. Standard formats (from FORMAT_REGISTRY)
"""

import json
from collections.abc import Sequence
from typing import Any

from src.core.database.database_session import get_db_session
from src.core.schemas import FORMAT_REGISTRY, Format


def _parse_format_from_db_row(row: Sequence[Any]) -> Format:
    """Extract Format object from database row.

    Args:
        row: Database tuple with format fields:
            (format_id, name, type, description, width, height,
             duration_seconds, max_file_size_kb, specs, is_standard, platform_config)

    Returns:
        Format object constructed from database row
    """
    # Parse JSON fields (handle both string and dict from SQLite vs PostgreSQL)
    specs = json.loads(row[8]) if isinstance(row[8], str) else row[8]
    platform_config_data: dict[str, Any] | None = None
    if row[10]:
        platform_config_data = json.loads(row[10]) if isinstance(row[10], str) else row[10]

    # Build requirements dict from database columns
    requirements: dict[str, Any] = {}
    if row[4]:  # width
        requirements["width"] = row[4]
    if row[5]:  # height
        requirements["height"] = row[5]
    if row[6]:  # duration_seconds
        requirements["duration_max"] = row[6]
    if row[7]:  # max_file_size_kb
        requirements["max_file_size_kb"] = row[7]

    # Merge with specs JSON
    if specs:
        requirements.update(specs)

    return Format(
        format_id=row[0],
        name=row[1],
        type=row[2],
        is_standard=bool(row[9]),
        iab_specification=None,  # Not stored in creative_formats table
        assets_required=None,  # Not stored in creative_formats table
        requirements=requirements if requirements else None,
        platform_config=platform_config_data,
    )


def get_format(format_id: str, tenant_id: str | None = None, product_id: str | None = None) -> Format:
    """Resolve format with priority: product override → tenant custom → standard registry.

    Args:
        format_id: Format identifier (e.g., "display_300x250")
        tenant_id: Optional tenant ID for custom format lookup
        product_id: Optional product ID for product-level overrides

    Returns:
        Format object with all configuration

    Raises:
        ValueError: If format_id not found in any source
    """
    # Check product override first
    if product_id and tenant_id:
        override = _get_product_format_override(tenant_id, product_id, format_id)
        if override:
            return override

    # Check tenant custom formats
    if tenant_id:
        custom = _get_tenant_custom_format(tenant_id, format_id)
        if custom:
            return custom

    # Fall back to standard registry
    if format_id in FORMAT_REGISTRY:
        return FORMAT_REGISTRY[format_id]

    # Not found anywhere
    error_msg = f"Unknown format_id '{format_id}'"
    if tenant_id:
        error_msg += f" for tenant {tenant_id}"
    raise ValueError(error_msg)


def _get_product_format_override(tenant_id: str, product_id: str, format_id: str) -> Format | None:
    """Get product-level format override from product.implementation_config.

    Product can override any format's platform_config. Example:
    {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {
                        "creative_placeholder": {
                            "width": 1,
                            "height": 1,
                            "creative_template_id": 12345678
                        }
                    }
                }
            }
        }
    }

    Args:
        tenant_id: Tenant identifier
        product_id: Product identifier
        format_id: Format to look up

    Returns:
        Format with overridden config, or None if no override exists
    """
    from sqlalchemy import text

    with get_db_session() as session:
        result = session.execute(
            text(
                "SELECT implementation_config FROM products WHERE tenant_id = :tenant_id AND product_id = :product_id"
            ),
            {"tenant_id": tenant_id, "product_id": product_id},
        )
        row = result.fetchone()
        if not row or not row[0]:
            return None

        # Parse implementation_config JSON
        impl_config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        format_overrides = impl_config.get("format_overrides", {})

        if format_id not in format_overrides:
            return None

        # Get base format (from tenant custom or standard registry)
        base_format = _get_tenant_custom_format(tenant_id, format_id) or FORMAT_REGISTRY.get(format_id)
        if not base_format:
            return None

        # Apply override to base format
        override_config = format_overrides[format_id]
        format_dict = base_format.model_dump()

        # Merge platform_config override
        if "platform_config" in override_config:
            base_platform_config = format_dict.get("platform_config") or {}
            override_platform_config = override_config["platform_config"]

            # Deep merge platform configs (override takes precedence)
            merged_platform_config = {**base_platform_config}
            for platform, config in override_platform_config.items():
                if platform in merged_platform_config:
                    # Merge platform-specific configs
                    merged_platform_config[platform] = {
                        **merged_platform_config[platform],
                        **config,
                    }
                else:
                    merged_platform_config[platform] = config

            format_dict["platform_config"] = merged_platform_config

        return Format(**format_dict)


def _get_tenant_custom_format(tenant_id: str, format_id: str) -> Format | None:
    """Get tenant-specific custom format from database.

    Tenants can define custom formats in the creative_formats table.
    Useful for non-standard sizes or platform-specific configurations.

    Args:
        tenant_id: Tenant identifier
        format_id: Format to look up

    Returns:
        Custom Format object, or None if not found
    """
    from sqlalchemy import text

    with get_db_session() as session:
        result = session.execute(
            text(
                """
                SELECT format_id, name, type, description, width, height,
                       duration_seconds, max_file_size_kb, specs, is_standard,
                       platform_config
                FROM creative_formats
                WHERE tenant_id = :tenant_id AND format_id = :format_id
            """
            ),
            {"tenant_id": tenant_id, "format_id": format_id},
        )
        row = result.fetchone()
        if not row:
            return None

        return _parse_format_from_db_row(row)


def list_available_formats(tenant_id: str | None = None) -> list[Format]:
    """List all formats available to a tenant (standard + custom).

    Args:
        tenant_id: Optional tenant ID to include custom formats

    Returns:
        List of all available Format objects
    """
    formats: list[Format] = []

    # Add standard formats
    formats.extend(FORMAT_REGISTRY.values())

    # Add tenant custom formats
    if tenant_id:
        from sqlalchemy import text

        with get_db_session() as session:
            result = session.execute(
                text(
                    """
                    SELECT format_id, name, type, description, width, height,
                           duration_seconds, max_file_size_kb, specs, is_standard,
                           platform_config
                    FROM creative_formats
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                """
                ),
                {"tenant_id": tenant_id},
            )

            for row in result.fetchall():
                formats.append(_parse_format_from_db_row(row))

    return formats
