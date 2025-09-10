"""Authentication utilities for MCP server."""

from fastmcp.server import Context
from rich.console import Console

from src.core.config_loader import set_current_tenant
from src.core.database.database_session import execute_with_retry
from src.core.database.models import Principal, Tenant

console = Console()


def get_principal_from_token(token: str, tenant_id: str | None = None) -> str | None:
    """Looks up a principal_id from the database using a token with retry logic.

    If tenant_id is provided, only looks in that specific tenant.
    If not provided, searches globally by token and sets the tenant context.

    Args:
        token: Authentication token
        tenant_id: Optional tenant ID to restrict search

    Returns:
        Principal ID if found, None otherwise
    """

    def _lookup_principal(session):
        if tenant_id:
            # If tenant_id specified, ONLY look in that tenant
            principal = session.query(Principal).filter_by(access_token=token, tenant_id=tenant_id).first()
            if principal:
                return principal.principal_id

            # Also check if it's the admin token for this specific tenant
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id, is_active=True).first()
            if tenant and token == tenant.admin_token:
                # Set tenant context for admin token
                tenant_dict = {
                    "tenant_id": tenant.tenant_id,
                    "name": tenant.name,
                    "subdomain": tenant.subdomain,
                    "ad_server": tenant.ad_server,
                }
                set_current_tenant(tenant_dict)
                return f"admin_{tenant.tenant_id}"
        else:
            # No tenant specified - search globally
            principal = session.query(Principal).filter_by(access_token=token).first()
            if principal:
                # Found principal - set tenant context
                tenant = session.query(Tenant).filter_by(tenant_id=principal.tenant_id, is_active=True).first()
                if tenant:
                    tenant_dict = {
                        "tenant_id": tenant.tenant_id,
                        "name": tenant.name,
                        "subdomain": tenant.subdomain,
                        "ad_server": tenant.ad_server,
                    }
                    set_current_tenant(tenant_dict)
                    return principal.principal_id

        return None

    try:
        return execute_with_retry(_lookup_principal)
    except Exception as e:
        console.print(f"[red]Database error during principal lookup: {e}[/red]")
        return None


def get_principal_from_context(context: Context | None) -> str | None:
    """Extract principal ID from the FastMCP context using x-adcp-auth header.

    Args:
        context: FastMCP context object

    Returns:
        Principal ID if authenticated, None otherwise
    """
    if not context:
        console.print("[yellow]DEBUG: No context provided[/yellow]")
        return None

    try:
        # Debug: Print context structure
        console.print(f"[yellow]DEBUG: Context type: {type(context)}[/yellow]")
        if hasattr(context, "meta"):
            console.print(f"[yellow]DEBUG: Context.meta: {context.meta}[/yellow]")
        if hasattr(context, "headers"):
            console.print(f"[yellow]DEBUG: Context.headers: {context.headers}[/yellow]")

        # Extract token from headers
        token = None
        if hasattr(context, "meta") and isinstance(context.meta, dict):
            headers = context.meta.get("headers", {})
            console.print(f"[yellow]DEBUG: Extracted headers from meta: {headers}[/yellow]")
            token = headers.get("x-adcp-auth")
        elif hasattr(context, "headers"):
            token = context.headers.get("x-adcp-auth")
            console.print(f"[yellow]DEBUG: Extracted token from context.headers: {token}[/yellow]")
        else:
            console.print("[yellow]DEBUG: No headers found in context[/yellow]")
            return None

        console.print(f"[yellow]DEBUG: Final extracted token: {token}[/yellow]")

        if not token:
            console.print("[yellow]DEBUG: No token found in headers[/yellow]")
            return None

        # Validate token and get principal ID
        principal_id = get_principal_from_token(token)
        console.print(f"[yellow]DEBUG: Token lookup result: {principal_id}[/yellow]")
        return principal_id

    except Exception as e:
        console.print(f"[red]Error extracting principal from context: {e}[/red]")
        return None


def get_principal_object(principal_id: str) -> Principal | None:
    """Get the Principal object with platform mappings using retry logic.

    Args:
        principal_id: The principal ID to look up

    Returns:
        Principal object or None if not found
    """
    if not principal_id:
        return None

    def _get_principal_object(session):
        from src.core.schemas import Principal as PrincipalSchema

        # Query the database for the principal
        db_principal = session.query(Principal).filter_by(principal_id=principal_id).first()

        if db_principal:
            # Convert to Pydantic model
            return PrincipalSchema(
                principal_id=db_principal.principal_id,
                name=db_principal.name,
                platform_mappings=db_principal.platform_mappings or {},
            )

        return None

    try:
        return execute_with_retry(_get_principal_object)
    except Exception as e:
        console.print(f"[red]Database error during principal object lookup: {e}[/red]")
        return None
