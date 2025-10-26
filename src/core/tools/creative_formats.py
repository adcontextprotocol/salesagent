"""AdCP tool implementation.

This module contains tool implementations following the MCP/A2A shared
implementation pattern from CLAUDE.md.
"""

import logging
import time

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import ValidationError

logger = logging.getLogger(__name__)

from src.core.audit_logger import get_audit_logger
from src.core.auth import get_principal_from_context
from src.core.config_loader import get_current_tenant, set_current_tenant
from src.core.schema_adapters import ListCreativeFormatsRequest, ListCreativeFormatsResponse
from src.core.validation_helpers import format_validation_error


def _list_creative_formats_impl(
    req: ListCreativeFormatsRequest | None, context: Context
) -> ListCreativeFormatsResponse:
    """List all available creative formats (AdCP spec endpoint).

    Returns formats from all registered creative agents (default + tenant-specific).
    Uses CreativeAgentRegistry for dynamic format discovery with caching.
    Supports optional filtering by type, standard_only, category, and format_ids.
    """
    start_time = time.time()

    # Use default request if none provided
    if req is None:
        req = ListCreativeFormatsRequest()

    # For discovery endpoints, authentication is optional
    # require_valid_token=False means invalid tokens are treated like missing tokens (discovery endpoint behavior)
    principal_id, tenant = get_principal_from_context(
        context, require_valid_token=False
    )  # Returns (None, tenant) if no/invalid auth

    # Set tenant context if returned
    if tenant:
        set_current_tenant(tenant)
    else:
        tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")

    # Get formats from all registered creative agents via registry
    import asyncio

    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()

    # Run async operation - check if we're already in an async context
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # We're in an async context, run in thread pool to avoid nested loop error
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(registry.list_all_formats(tenant_id=tenant["tenant_id"])))
            formats = future.result()
    except RuntimeError:
        # No running loop, safe to create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            formats = loop.run_until_complete(registry.list_all_formats(tenant_id=tenant["tenant_id"]))
        finally:
            loop.close()

    # Apply filters from request
    if req.type:
        formats = [f for f in formats if f.type == req.type]

    if req.standard_only:
        formats = [f for f in formats if f.is_standard]

    if req.category:
        # Category maps to is_standard: "standard" -> True, "custom" -> False
        if req.category == "standard":
            formats = [f for f in formats if f.is_standard]
        elif req.category == "custom":
            formats = [f for f in formats if not f.is_standard]

    if req.format_ids:
        # Filter to only the specified format IDs
        # Extract the 'id' field from each FormatId object
        format_ids_set = {fmt.id for fmt in req.format_ids}
        # Compare format_id.id (handle both FormatId objects and strings)
        formats = [
            f for f in formats if (f.format_id.id if hasattr(f.format_id, "id") else f.format_id) in format_ids_set
        ]

    # Sort formats by type and name for consistent ordering
    formats.sort(key=lambda f: (f.type, f.name))

    # Log the operation
    audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
    audit_logger.log_operation(
        operation="list_creative_formats",
        principal_name=principal_id or "anonymous",
        principal_id=principal_id or "anonymous",
        adapter_id="N/A",
        success=True,
        details={
            "format_count": len(formats),
            "standard_formats": len([f for f in formats if f.is_standard]),
            "custom_formats": len([f for f in formats if not f.is_standard]),
            "format_types": list({f.type for f in formats}),
        },
    )

    # Create response (no message/specification_version - not in adapter schema)
    response = ListCreativeFormatsResponse(formats=formats)

    # Add schema validation metadata for client validation
    from src.core.schema_validation import INCLUDE_SCHEMAS_IN_RESPONSES, enhance_mcp_response_with_schema

    if INCLUDE_SCHEMAS_IN_RESPONSES:
        # Convert to dict, enhance with schema, return enhanced dict
        response_dict = response.model_dump()
        enhanced_response = enhance_mcp_response_with_schema(
            response_data=response_dict,
            model_class=ListCreativeFormatsResponse,
            include_full_schema=False,  # Set to True for development debugging
        )
        # Return the enhanced response (FastMCP handles dict returns)
        return enhanced_response

    return response


def list_creative_formats(
    type: str | None = None,
    standard_only: bool | None = None,
    category: str | None = None,
    format_ids: list[str] | None = None,
    webhook_url: str | None = None,
    context: Context = None,
) -> ListCreativeFormatsResponse:
    """List all available creative formats (AdCP spec endpoint).

    MCP tool wrapper that delegates to the shared implementation.

    Args:
        type: Filter by format type (audio, video, display)
        standard_only: Only return IAB standard formats
        category: Filter by format category (standard, custom)
        format_ids: Filter by specific format IDs
        webhook_url: URL for async task completion notifications (AdCP spec, optional)
        context: FastMCP context (automatically provided)

    Returns:
        ListCreativeFormatsResponse with all available formats
    """
    try:
        req = ListCreativeFormatsRequest(
            type=type,
            standard_only=standard_only,
            category=category,
            format_ids=format_ids,
        )
    except ValidationError as e:
        raise ToolError(format_validation_error(e, context="list_creative_formats request")) from e

    return _list_creative_formats_impl(req, context)


def list_creative_formats_raw(
    req: ListCreativeFormatsRequest | None = None, context: Context = None
) -> ListCreativeFormatsResponse:
    """List all available creative formats (raw function for A2A server use).

    Delegates to shared implementation.

    Args:
        req: Optional request with filter parameters
        context: FastMCP context

    Returns:
        ListCreativeFormatsResponse with all available formats
    """
    return _list_creative_formats_impl(req, context)
