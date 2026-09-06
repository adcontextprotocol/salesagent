"""AdCP tool implementation.

This module contains tool implementations following the MCP/A2A shared
implementation pattern from CLAUDE.md.
"""

import logging

from adcp.types import ContextObject
from fastmcp.server.context import Context

from src.core.tool_context import ToolContext

logger = logging.getLogger(__name__)

from src.core.audit_logger import get_audit_logger
from src.core.auth import require_identity, require_principal_id, require_tenant, resolve_principal_or_raise
from src.core.database.repositories import MediaBuyUoW
from src.core.helpers.adapter_helpers import get_adapter
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import (
    PackagePerformance,
    ProductPerformance,
    UpdatePerformanceIndexRequest,
    UpdatePerformanceIndexResponse,
)
from src.core.tools._mcp import mcp_result
from src.core.tools.media_buy_update import _verify_principal


def _build_update_performance_index_request(
    media_buy_id: str,
    performance_data: list[ProductPerformance],
    context: ContextObject | None = None,
) -> UpdatePerformanceIndexRequest:
    """Build an UpdatePerformanceIndexRequest from individual wire params.

    Entries arrive TYPED from MCP -- the advertised shape derives from the DTO, whose
    performance_data is list[ProductPerformance], so FastMCP validates the buyer's JSON into
    models before the call -- and as raw dicts from A2A and REST, which hand the builder the
    wire payload. model_validate reads both; ``ProductPerformance(**perf)`` read only dicts
    and raised ``argument after ** must be a mapping, not ProductPerformance`` on MCP,
    i.e. an untyped 500 on the exact payload our published schema documents.

    This is the second instance of one class: the DTO's TYPE is adopted at the boundary while
    the builder stays narrow. The first was update_media_buy.budget. Both were named in a
    27-entry type-divergence ledger that was deleted rather than worked through -- correctly,
    since a type mismatch is a bug and not something to record, but the deletion only settled
    the entry that had a test.
    """
    performance_objects = [ProductPerformance.model_validate(perf) for perf in performance_data]
    return UpdatePerformanceIndexRequest(
        media_buy_id=media_buy_id, performance_data=performance_objects, context=context
    )


def _update_performance_index_impl(
    req: UpdatePerformanceIndexRequest,
    identity: ResolvedIdentity | None = None,
) -> UpdatePerformanceIndexResponse:
    """Shared implementation for update_performance_index (used by both MCP and A2A).

    Args:
        req: Typed update-performance-index request
        identity: Resolved identity for authentication

    Returns:
        UpdatePerformanceIndexResponse with update status
    """
    identity = require_identity(identity, context=req.context)

    # Tenant is resolved at the transport boundary (resolve_identity_from_context)
    tenant = require_tenant(identity, context=req.context)

    with MediaBuyUoW(tenant["tenant_id"]) as uow:
        assert uow.media_buys is not None
        _verify_principal(req.media_buy_id, identity, uow.media_buys, context=req.context)
    principal_id = require_principal_id(identity, context=req.context)

    principal = resolve_principal_or_raise(principal_id, tenant_id=identity.tenant_id, context=req.context)

    # Get the appropriate adapter (no dry_run support for performance updates)
    adapter = get_adapter(principal, dry_run=False, tenant=tenant)

    # Convert ProductPerformance to PackagePerformance for the adapter
    package_performance = [
        PackagePerformance(package_id=perf.product_id, performance_index=perf.performance_index)
        for perf in req.performance_data
    ]

    # Call the adapter's update method
    success = adapter.update_media_buy_performance_index(req.media_buy_id, package_performance)

    # Log the performance update
    logger.info("Performance Index Update for %s", req.media_buy_id)
    for perf in req.performance_data:
        logger.info(
            "  %s: %.2f (confidence: %s)",
            perf.product_id,
            perf.performance_index,
            perf.confidence_score or "N/A",
        )

    if any(p.performance_index < 0.8 for p in req.performance_data):
        logger.info("Low performance detected for %s - optimization recommended", req.media_buy_id)

    # Log the update_performance_index call
    audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
    audit_logger.log_operation(
        operation="update_performance_index",
        principal_name=principal_id or "anonymous",
        principal_id=principal_id or "anonymous",
        adapter_id="mcp_server",
        success=success,
        details={
            "media_buy_id": req.media_buy_id,
            "product_count": len(req.performance_data),
            "avg_performance_index": (
                sum(p.performance_index for p in req.performance_data) / len(req.performance_data)
                if req.performance_data
                else 0
            ),
        },
    )

    return UpdatePerformanceIndexResponse(
        status="success" if success else "failed",
        detail=f"Performance index updated for {len(req.performance_data)} products",
        context=req.context,
    )


async def update_performance_index(
    media_buy_id: str,
    performance_data: list[ProductPerformance],
    context: ContextObject | None = None,
    ctx: Context | ToolContext | None = None,
):
    """Update performance index data for a media buy.

    MCP tool wrapper that delegates to the shared implementation.
    FastMCP automatically validates and coerces JSON inputs to Pydantic models.

    Args:
        media_buy_id: ID of the media buy to update
        performance_data: List of performance data objects
        ctx: FastMCP context (automatically provided)

    Returns:
        ToolResult with UpdatePerformanceIndexResponse data
    """
    identity = (await ctx.get_state("identity")) if isinstance(ctx, Context) else None
    req = _build_update_performance_index_request(media_buy_id, performance_data, context)
    response = _update_performance_index_impl(req=req, identity=identity)
    return mcp_result(response)


# --- Human-in-the-Loop Task Queue Tools ---
# DEPRECATED workflow functions moved to src/core/helpers/workflow_helpers.py and imported above

# Removed get_pending_workflows - replaced by admin dashboard workflow views

# Removed assign_task - assignment handled through admin UI workflow management

# Dry run logs are now handled by the adapters themselves
