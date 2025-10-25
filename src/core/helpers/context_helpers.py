"""Context extraction helpers for MCP tools."""

from fastmcp.server.context import Context

from src.core.auth import get_principal_from_context
from src.core.config_loader import set_current_tenant


def get_principal_id_from_context(context: Context | None) -> str | None:
    """Extract principal ID from context.

    Wrapper around get_principal_from_context that returns just the principal_id
    and sets the tenant context.

    Args:
        context: FastMCP context

    Returns:
        Principal ID string, or None if not authenticated
    """
    principal_id, tenant = get_principal_from_context(context)
    # Set tenant context if found
    if tenant:
        set_current_tenant(tenant)
    return principal_id
