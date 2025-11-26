"""Shared domain routing logic for landing pages.

Centralizes the logic for determining how to route requests based on domain:
- Custom domains (virtual_host) → agent landing page
- Subdomains (*.sales-agent.scope3.com) → agent landing page or login
- Admin domains (admin.*) → admin login
- Unknown domains → fallback

Used by both MCP server and Admin UI to ensure consistent behavior.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant
from src.core.domain_config import extract_subdomain_from_host, is_sales_agent_domain


@dataclass
class RoutingResult:
    """Result of domain routing decision.

    Attributes:
        type: Type of routing decision (custom_domain, subdomain, admin, unknown)
        tenant: Tenant dict if found, None otherwise
        effective_host: The host used for routing decision
    """

    type: Literal["custom_domain", "subdomain", "admin", "unknown"]
    tenant: dict | None
    effective_host: str


def get_tenant_by_virtual_host(virtual_host: str) -> dict | None:
    """Look up tenant by virtual_host (custom domain).

    Args:
        virtual_host: Custom domain to look up (e.g., "sales-agent.accuweather.com")

    Returns:
        Tenant dict with keys: tenant_id, name, subdomain, virtual_host
        Returns None if no tenant found
    """
    with get_db_session() as db_session:
        stmt = select(Tenant).filter_by(virtual_host=virtual_host, is_active=True)
        tenant_obj = db_session.scalars(stmt).first()
        if tenant_obj:
            return {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "subdomain": tenant_obj.subdomain,
                "virtual_host": tenant_obj.virtual_host,
            }
    return None


def get_tenant_by_subdomain(subdomain: str) -> dict | None:
    """Look up tenant by subdomain.

    Args:
        subdomain: Subdomain to look up (e.g., "accuweather")

    Returns:
        Tenant dict with keys: tenant_id, name, subdomain, virtual_host
        Returns None if no tenant found
    """
    with get_db_session() as db_session:
        stmt = select(Tenant).filter_by(subdomain=subdomain, is_active=True)
        tenant_obj = db_session.scalars(stmt).first()
        if tenant_obj:
            return {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "subdomain": tenant_obj.subdomain,
                "virtual_host": tenant_obj.virtual_host,
            }
    return None


def route_landing_page(request_headers: dict) -> RoutingResult:
    """Determine landing page routing based on request headers.

    This function centralizes all domain routing logic used by both
    MCP server and Admin UI. It examines headers to determine:
    1. What type of domain is being accessed
    2. Whether a tenant exists for that domain
    3. What the appropriate response should be

    Args:
        request_headers: Dict of HTTP headers (case-insensitive keys supported)

    Returns:
        RoutingResult indicating routing decision and tenant if found

    Routing logic:
    - Admin domains (admin.*) → type="admin"
    - Custom domains (not sales-agent domain) with tenant → type="custom_domain"
    - Sales-agent subdomains with tenant → type="subdomain"
    - Everything else → type="unknown"
    """
    # Get host from headers (Approximated proxy or direct)
    apx_host = request_headers.get("apx-incoming-host") or request_headers.get("Apx-Incoming-Host")
    host_header = request_headers.get("host") or request_headers.get("Host")

    # Use whichever host is available (proxy header takes precedence)
    effective_host = apx_host or host_header

    if not effective_host:
        return RoutingResult("unknown", None, "")

    # Admin domain check
    if effective_host.startswith("admin."):
        return RoutingResult("admin", None, effective_host)

    # Custom domain check (non-sales-agent domain)
    if not is_sales_agent_domain(effective_host):
        tenant = get_tenant_by_virtual_host(effective_host)
        return RoutingResult("custom_domain", tenant, effective_host)

    # Subdomain check (sales-agent domain with subdomain)
    subdomain = extract_subdomain_from_host(effective_host)
    tenant = get_tenant_by_subdomain(subdomain) if subdomain else None
    return RoutingResult("subdomain", tenant, effective_host)
