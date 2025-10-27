"""AdCP tool implementation.

This module contains tool implementations following the MCP/A2A shared
implementation pattern from CLAUDE.md.
"""

import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import ValidationError
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

from src.core.auth import get_principal_object
from src.core.helpers.adapter_helpers import get_adapter
from src.core.helpers.context_helpers import get_principal_id_from_context as _get_principal_id_from_context
from src.core.schemas import PackagePerformance, UpdatePerformanceIndexRequest, UpdatePerformanceIndexResponse
from src.core.tools.media_buy_update import _verify_principal
from src.core.validation_helpers import format_validation_error


def update_performance_index(
    media_buy_id: str, performance_data: list[dict[str, Any]], webhook_url: str | None = None, context: Context = None
) -> UpdatePerformanceIndexResponse:
    """Update performance index data for a media buy.

    Args:
        media_buy_id: ID of the media buy to update
        performance_data: List of performance data objects
        webhook_url: URL for async task completion notifications (AdCP spec, optional)
        context: FastMCP context (automatically provided)

    Returns:
        UpdatePerformanceIndexResponse with operation status
    """
    # Create request object from individual parameters (MCP-compliant)
    # Convert dict performance_data to ProductPerformance objects
    from src.core.schemas import ProductPerformance

    try:
        performance_objects = [ProductPerformance(**perf) for perf in performance_data]
        req = UpdatePerformanceIndexRequest(media_buy_id=media_buy_id, performance_data=performance_objects)
    except ValidationError as e:
        raise ToolError(format_validation_error(e, context="update_performance_index request")) from e

    if context is None:
        raise ValueError("Context is required for update_performance_index")

    _verify_principal(req.media_buy_id, context)
    principal_id = _get_principal_id_from_context(context)  # Already verified by _verify_principal

    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        return UpdatePerformanceIndexResponse(
            status="failed",
            message=f"Principal {principal_id} not found",
            errors=[{"code": "principal_not_found", "message": f"Principal {principal_id} not found"}],
        )

    # Get the appropriate adapter (no dry_run support for performance updates)
    adapter = get_adapter(principal, dry_run=False)

    # Convert ProductPerformance to PackagePerformance for the adapter
    package_performance = [
        PackagePerformance(package_id=perf.product_id, performance_index=perf.performance_index)
        for perf in req.performance_data
    ]

    # Call the adapter's update method
    success = adapter.update_media_buy_performance_index(req.media_buy_id, package_performance)

    # Log the performance update
    console.print(f"[bold green]Performance Index Update for {req.media_buy_id}:[/bold green]")
    for perf in req.performance_data:
        status_emoji = "📈" if perf.performance_index > 1.0 else "📉" if perf.performance_index < 1.0 else "➡️"
        console.print(
            f"  {status_emoji} {perf.product_id}: {perf.performance_index:.2f} (confidence: {perf.confidence_score or 'N/A'})"
        )

    # Simulate optimization based on performance
    if any(p.performance_index < 0.8 for p in req.performance_data):
        console.print("  [yellow]⚠️  Low performance detected - optimization recommended[/yellow]")

    return UpdatePerformanceIndexResponse(
        status="success" if success else "failed",
        detail=f"Performance index updated for {len(req.performance_data)} products",
    )


def update_performance_index_raw(media_buy_id: str, performance_data: list[dict[str, Any]], context: Context = None):
    """Update performance data for a media buy (raw function for A2A server use).

    Delegates to the shared implementation.

    Args:
        media_buy_id: The ID of the media buy to update performance for
        performance_data: List of performance data objects
        context: Context for authentication

    Returns:
        UpdatePerformanceIndexResponse
    """
    return update_performance_index(media_buy_id, performance_data, webhook_url=None, context=context)


# --- Human-in-the-Loop Task Queue Tools ---
# DEPRECATED workflow functions moved to src/core/helpers/workflow_helpers.py and imported above

# Removed get_pending_workflows - replaced by admin dashboard workflow views

# Removed assign_task - assignment handled through admin UI workflow management

# Dry run logs are now handled by the adapters themselves
