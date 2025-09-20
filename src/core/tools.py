"""
Raw AdCP tool functions without FastMCP decorators.

This module provides direct access to the core AdCP functions without
FastMCP tool decorators, specifically for use by the A2A server.
The functions here are the same implementation as in main.py but without
the @mcp.tool decorators.
"""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context

from src.core.testing_hooks import (
    get_testing_context,
)

logger = logging.getLogger(__name__)

# Database models

# Other imports
from src.core.config_loader import (
    get_current_tenant,
    get_tenant_by_virtual_host,
    safe_json_loads,
)
from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ModelProduct

# Schema models (explicit imports to avoid collisions)
from src.core.schemas import (
    CreateMediaBuyResponse,
    GetProductsResponse,
    GetSignalsRequest,
    GetSignalsResponse,
    ListCreativesResponse,
    Product,
    SyncCreativesResponse,
)


def get_principal_from_context(context: Context | None) -> str | None:
    """Extract principal ID from the FastMCP context using x-adcp-auth header."""
    if not context:
        return None

    try:
        # Get headers from FastMCP context metadata
        headers = context.meta.get("headers", {}) if hasattr(context, "meta") else {}
        if not headers:
            return None

        # Get the x-adcp-auth header (FastMCP forwards this in context.meta)
        auth_token = headers.get("x-adcp-auth")
        if not auth_token:
            return None

        # Look up principal by token
        from src.core.auth_utils import get_principal_from_token

        return get_principal_from_token(auth_token)

    except Exception as e:
        logger.warning(f"Error extracting principal from context: {e}")
        return None


async def get_products_raw(brief: str, promoted_offering: str, context: Context = None) -> GetProductsResponse:
    """Get available products matching the brief.

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        brief: Brief description of the advertising campaign or requirements
        promoted_offering: What is being promoted/advertised (required per AdCP spec)
        context: FastMCP context (automatically provided)

    Returns:
        GetProductsResponse containing matching products
    """
    # Import the implementation from main.py and call it
    # We can't import the decorated function directly, so we'll implement it here

    # Use ToolContext if available
    if hasattr(context, "tenant_id") and hasattr(context, "principal_id"):
        # ToolContext provided directly
        principal_id = context.principal_id
        tenant = {"tenant_id": context.tenant_id}  # Simplified tenant info
    else:
        # Legacy path - extract from FastMCP Context
        testing_ctx = get_testing_context(context)
        # For discovery endpoints, authentication is optional
        principal_id = get_principal_from_context(context)  # Returns None if no auth

        # Get tenant info - required for product lookup
        tenant = get_current_tenant()
        if not tenant:
            # Try to get tenant from virtual host if context available
            if context and hasattr(context, "meta") and context.meta.get("headers"):
                headers = context.meta["headers"]
                host = headers.get("host", "").split(":")[0]  # Remove port if present
                tenant = get_tenant_by_virtual_host(host)

        if not tenant:
            raise ToolError("No tenant configuration found", "NO_TENANT")

    # Get tenant ID
    tenant_id = tenant["tenant_id"]

    # Load products from database
    logger.info(f"Loading products for tenant {tenant_id}")
    with get_db_session() as session:
        db_products = session.query(ModelProduct).filter_by(tenant_id=tenant_id).all()

    # Convert to schema objects and filter based on brief
    products = []
    for db_product in db_products:
        product_data = {
            "product_id": db_product.product_id,
            "name": db_product.name,
            "description": db_product.description or "",
            "formats": safe_json_loads(db_product.formats, []),
            "delivery_type": db_product.delivery_type,
            "is_fixed_price": db_product.is_fixed_price,
            "cpm": float(db_product.cpm) if db_product.cpm else None,
            "min_spend": float(db_product.min_spend) if db_product.min_spend else None,
            "measurement": safe_json_loads(db_product.measurement, None) if db_product.measurement else None,
            "creative_policy": (
                safe_json_loads(db_product.creative_policy, None) if db_product.creative_policy else None
            ),
            "is_custom": db_product.is_custom or False,
            "expires_at": db_product.expires_at,
            "implementation_config": (
                safe_json_loads(db_product.implementation_config, None) if db_product.implementation_config else None
            ),
        }
        products.append(Product(**product_data))

    # Simple filtering based on brief (can be enhanced)
    if brief:
        brief_lower = brief.lower()
        filtered_products = []
        for product in products:
            # Convert format IDs to Format objects for proper type checking
            from src.core.schemas import convert_format_ids_to_formats

            format_objects = convert_format_ids_to_formats(product.formats)

            if (
                brief_lower in product.name.lower()
                or brief_lower in product.description.lower()
                or any(brief_lower in fmt.type.lower() for fmt in format_objects)
                or any(brief_lower in fmt_id.lower() for fmt_id in product.formats)
            ):
                filtered_products.append(product)

        if filtered_products:
            products = filtered_products

    message = f"Found {len(products)} matching products for your requirements"
    return GetProductsResponse(products=products, message=message)


async def get_signals_raw(req: GetSignalsRequest, context: Context = None) -> GetSignalsResponse:
    """Optional endpoint for discovering available signals (audiences, contextual, etc.)

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        req: Request containing query parameters for signal discovery
        context: FastMCP context (automatically provided)

    Returns:
        GetSignalsResponse containing matching signals
    """
    # Use ToolContext if available
    if hasattr(context, "tenant_id") and hasattr(context, "principal_id"):
        tenant_id = context.tenant_id
        principal_id = context.principal_id
    else:
        # Legacy path - extract from FastMCP Context
        principal_id = get_principal_from_context(context)
        tenant = get_current_tenant()
        if not tenant:
            raise ToolError("No tenant configuration found", "NO_TENANT")
        tenant_id = tenant["tenant_id"]

    # Get available signals from configuration
    signals = []

    # Add some basic signals as example
    from src.core.schemas import Signal, SignalDeployment, SignalPricing

    basic_signals = [
        {
            "signal_id": "age_18_24",
            "name": "Age 18-24",
            "description": "Audience aged 18-24 years",
            "category": "demographics",
            "signal_type": "audience",
            "deployments": [
                SignalDeployment(
                    provider="internal",
                    provider_signal_id="age_18_24",
                    supported_platforms=["gam", "kevel"],
                    availability="available",
                )
            ],
            "pricing": [SignalPricing(provider="internal", cost_type="cpm_multiplier", cost_value=1.2, currency="USD")],
        },
        {
            "signal_id": "sports_interest",
            "name": "Sports Interest",
            "description": "Users interested in sports content",
            "category": "interests",
            "signal_type": "audience",
            "deployments": [
                SignalDeployment(
                    provider="internal",
                    provider_signal_id="sports_interest",
                    supported_platforms=["gam"],
                    availability="available",
                )
            ],
            "pricing": [SignalPricing(provider="internal", cost_type="cpm_multiplier", cost_value=1.1, currency="USD")],
        },
    ]

    # Filter by signal types if specified
    if req.signal_types:
        basic_signals = [s for s in basic_signals if s["signal_type"] in req.signal_types]

    # Filter by categories if specified
    if req.categories:
        basic_signals = [s for s in basic_signals if s["category"] in req.categories]

    # Convert to Signal objects
    for signal_data in basic_signals:
        signal = Signal(**signal_data)
        signals.append(signal)

    return GetSignalsResponse(signals=signals)


def create_media_buy_raw(
    po_number: str,
    buyer_ref: str = None,
    packages: list = None,
    start_time: str = None,
    end_time: str = None,
    product_ids: list[str] = None,
    total_budget: float = None,
    start_date: str = None,
    end_date: str = None,
    targeting_overlay: dict = None,
    context: Context = None,
) -> CreateMediaBuyResponse:
    """Create a new media buy with specified parameters.

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        po_number: Purchase order number
        buyer_ref: Buyer reference identifier
        packages: List of media packages (optional)
        start_time: Start time (legacy parameter)
        end_time: End time (legacy parameter)
        product_ids: List of product IDs to include
        total_budget: Total budget for the media buy
        start_date: Flight start date (YYYY-MM-DD)
        end_date: Flight end date (YYYY-MM-DD)
        targeting_overlay: Additional targeting parameters
        context: FastMCP context (automatically provided)

    Returns:
        CreateMediaBuyResponse with media buy details
    """
    # Use ToolContext if available
    if hasattr(context, "tenant_id") and hasattr(context, "principal_id"):
        tenant_id = context.tenant_id
        principal_id = context.principal_id
    else:
        # Legacy path - extract from FastMCP Context
        principal_id = get_principal_from_context(context)
        if not principal_id:
            raise ToolError("Authentication required for media buy creation", "AUTH_REQUIRED")

        tenant = get_current_tenant()
        if not tenant:
            raise ToolError("No tenant configuration found", "NO_TENANT")
        tenant_id = tenant["tenant_id"]

    # Generate media buy ID
    media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"

    # Default values
    if not buyer_ref:
        buyer_ref = f"buyer_{principal_id}_{int(time.time())}"

    if not start_date and start_time:
        start_date = start_time
    if not end_date and end_time:
        end_date = end_time

    if not start_date:
        start_date = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    if not end_date:
        start_dt = datetime.fromisoformat(start_date).date()
        end_date = (start_dt + timedelta(days=30)).isoformat()

    if not total_budget:
        total_budget = 10000.0

    if not product_ids:
        product_ids = []

    # Create response
    response = CreateMediaBuyResponse(
        media_buy_id=media_buy_id,
        status="created",
        message=f"Media buy {media_buy_id} created successfully",
        packages=[],  # Empty for now
        buyer_ref=buyer_ref,
        po_number=po_number,
        flight_start_date=start_date,
        flight_end_date=end_date,
        total_budget=total_budget,
    )

    return response


def sync_creatives_raw(
    creatives: list[dict],
    media_buy_id: str = None,
    buyer_ref: str = None,
    assign_to_packages: list[str] = None,
    upsert: bool = True,
    context: Context = None,
) -> SyncCreativesResponse:
    """Sync creative assets to the centralized creative library (AdCP spec endpoint).

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        creatives: List of creative asset objects
        media_buy_id: Media buy ID for the creatives (optional)
        buyer_ref: Buyer's reference for the media buy (optional)
        assign_to_packages: Package IDs to assign creatives to (optional)
        upsert: Whether to update existing creatives or create new ones
        context: FastMCP context (automatically provided)

    Returns:
        SyncCreativesResponse with synced creatives and assignments
    """
    # Use ToolContext if available
    if hasattr(context, "tenant_id") and hasattr(context, "principal_id"):
        tenant_id = context.tenant_id
        principal_id = context.principal_id
    else:
        # Legacy path - extract from FastMCP Context
        principal_id = get_principal_from_context(context)
        if not principal_id:
            raise ToolError("Authentication required for creative sync", "AUTH_REQUIRED")

        tenant = get_current_tenant()
        if not tenant:
            raise ToolError("No tenant configuration found", "NO_TENANT")
        tenant_id = tenant["tenant_id"]

    synced_creatives = []
    failed_creatives = []
    assignments = []

    # Process each creative
    for creative_data in creatives:
        try:
            # Generate creative ID if not provided
            if "creative_id" not in creative_data:
                creative_data["creative_id"] = f"cr_{uuid.uuid4().hex[:8]}"

            # Set default status
            if "status" not in creative_data:
                creative_data["status"] = "pending_review"

            # Add to synced list
            from src.core.schemas import Creative

            creative = Creative(**creative_data)
            synced_creatives.append(creative)

        except Exception as e:
            failed_creatives.append({"creative_data": creative_data, "error": str(e)})

    message = f"Synced {len(synced_creatives)} creatives, {len(failed_creatives)} failed"

    return SyncCreativesResponse(
        synced_creatives=synced_creatives,
        failed_creatives=failed_creatives,
        assignments=assignments,
        message=message,
    )


def list_creatives_raw(
    media_buy_id: str = None,
    buyer_ref: str = None,
    status: str = None,
    format: str = None,
    tags: list[str] = None,
    created_after: str = None,
    created_before: str = None,
    search: str = None,
    page: int = 1,
    limit: int = 50,
    sort_by: str = "created_date",
    sort_order: str = "desc",
    context: Context = None,
) -> ListCreativesResponse:
    """List creative assets with filtering and pagination (AdCP spec endpoint).

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        media_buy_id: Filter by media buy ID (optional)
        buyer_ref: Filter by buyer reference (optional)
        status: Filter by status (pending_review, approved, rejected, etc.) (optional)
        format: Filter by creative format (optional)
        tags: Filter by creative group tags (optional)
        created_after: Filter creatives created after this date (ISO format) (optional)
        created_before: Filter creatives created before this date (ISO format) (optional)
        search: Search in creative name or description (optional)
        page: Page number for pagination (default: 1)
        limit: Number of results per page (default: 50, max: 1000)
        sort_by: Sort field (created_date, name, status) (default: created_date)
        sort_order: Sort order (asc, desc) (default: desc)
        context: FastMCP context (automatically provided)

    Returns:
        ListCreativesResponse with filtered creative assets and pagination info
    """
    # Use ToolContext if available
    if hasattr(context, "tenant_id") and hasattr(context, "principal_id"):
        tenant_id = context.tenant_id
        principal_id = context.principal_id
    else:
        # Legacy path - extract from FastMCP Context
        principal_id = get_principal_from_context(context)
        if not principal_id:
            raise ToolError("Authentication required for listing creatives", "AUTH_REQUIRED")

        tenant = get_current_tenant()
        if not tenant:
            raise ToolError("No tenant configuration found", "NO_TENANT")
        tenant_id = tenant["tenant_id"]

    # For now, return empty list - full implementation would query database
    creatives = []
    total_count = 0
    has_more = False

    message = f"Found {total_count} creatives matching your criteria"

    return ListCreativesResponse(
        creatives=creatives,
        total_count=total_count,
        page=page,
        limit=limit,
        has_more=has_more,
        message=message,
    )
