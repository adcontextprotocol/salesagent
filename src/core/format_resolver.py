"""Format resolution with product overrides and dynamic creative agent discovery.

Provides layered format lookup:
1. Product-level overrides (from product.implementation_config.format_overrides)
2. Dynamic format discovery from creative agents (via CreativeAgentRegistry)

Note: Tenant custom formats (creative_formats table) are deprecated in favor of
creative agent-based format discovery per AdCP v2.4.
"""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from src.core.database.database_session import get_db_session
from src.core.schemas import Format, FormatId


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
        format_id=FormatId(agent_url="https://creative.adcontextprotocol.org", id=row[0]),
        name=row[1],
        type=row[2],
        is_standard=bool(row[9]),
        iab_specification=None,  # Not stored in creative_formats table
        assets_required=None,  # Not stored in creative_formats table
        requirements=requirements if requirements else None,
        platform_config=platform_config_data,
    )


def get_format(
    format_id: str, agent_url: str | None = None, tenant_id: str | None = None, product_id: str | None = None
) -> Format:
    """Resolve format with priority: product override → creative agent discovery.

    Args:
        format_id: Format identifier (e.g., "display_300x250_image")
        agent_url: Optional creative agent URL (defaults to AdCP standard agent)
        tenant_id: Optional tenant ID for agent lookup
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

    # Get from creative agent registry
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()

    # If agent_url provided, get format directly from that agent
    if agent_url:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            fmt = loop.run_until_complete(registry.get_format(agent_url, format_id))
            if fmt:
                return fmt
        finally:
            loop.close()
    else:
        # Search all agents for this format
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            all_formats = loop.run_until_complete(registry.list_all_formats(tenant_id=tenant_id))
            for fmt in all_formats:
                if fmt.format_id == format_id:
                    return fmt
        finally:
            loop.close()

    # Not found anywhere
    error_msg = f"Unknown format_id '{format_id}'"
    if agent_url:
        error_msg += f" from agent {agent_url}"
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

        # Get base format from creative agent registry
        try:
            base_format = get_format(format_id, tenant_id=tenant_id)
        except ValueError:
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


def list_available_formats(
    tenant_id: str | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    is_responsive: bool | None = None,
    asset_types: list[str] | None = None,
    name_search: str | None = None,
    type_filter: str | None = None,
) -> list[Format]:
    """List all formats available to a tenant from all registered creative agents.

    Args:
        tenant_id: Optional tenant ID to include tenant-specific agents
        max_width: Maximum width in pixels (inclusive)
        max_height: Maximum height in pixels (inclusive)
        min_width: Minimum width in pixels (inclusive)
        min_height: Minimum height in pixels (inclusive)
        is_responsive: Filter for responsive formats
        asset_types: Filter by asset types
        name_search: Search by name
        type_filter: Filter by format type (display, video, audio)

    Returns:
        List of all available Format objects from all registered agents
    """
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()

    # Get formats from all agents (default + tenant-specific)
    # Check if we're already in an async context
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, cannot use run_until_complete
        # Return a coroutine that needs to be awaited
        import warnings

        warnings.warn(
            "list_available_formats() called from async context. "
            "Use await registry.list_all_formats() directly instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # For backward compatibility, run in thread pool
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(
                    registry.list_all_formats(
                        tenant_id=tenant_id,
                        max_width=max_width,
                        max_height=max_height,
                        min_width=min_width,
                        min_height=min_height,
                        is_responsive=is_responsive,
                        asset_types=asset_types,
                        name_search=name_search,
                        type_filter=type_filter,
                    )
                )
            )
            formats = future.result()
    except RuntimeError:
        # No running loop, we can safely create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            formats = loop.run_until_complete(
                registry.list_all_formats(
                    tenant_id=tenant_id,
                    max_width=max_width,
                    max_height=max_height,
                    min_width=min_width,
                    min_height=min_height,
                    is_responsive=is_responsive,
                    asset_types=asset_types,
                    name_search=name_search,
                    type_filter=type_filter,
                )
            )
        finally:
            loop.close()

    return formats
