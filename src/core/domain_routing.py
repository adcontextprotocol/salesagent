"""Shared domain routing logic for landing pages.

Centralizes the logic for determining how to route requests based on domain:
- Custom domains (virtual_host) → agent landing page
- Subdomains (*.sales-agent.scope3.com) → agent landing page or login
- Admin domains (admin.*) → admin login
- Unknown domains → fallback

Used by MCP server, Admin UI, and A2A server to ensure consistent behavior.
"""

from dataclasses import dataclass
from typing import Literal

# Import existing tenant lookup functions from config_loader
# This ensures all servers (MCP, Admin, A2A) use the same lookup logic
from src.core.config_loader import (
    get_tenant_by_subdomain,
    get_tenant_by_virtual_host,
)
from src.core.domain_config import (
    extract_subdomain_from_host,
    is_admin_domain,
    is_sales_agent_domain,
)


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

    # Admin domain check - must be exact match to prevent spoofing
    # (e.g., admin.sales-agent.scope3.com, NOT admin.malicious.com)
    if is_admin_domain(effective_host):
        return RoutingResult("admin", None, effective_host)

    # Custom domain check (non-sales-agent domain)
    if not is_sales_agent_domain(effective_host):
        tenant = get_tenant_by_virtual_host(effective_host)
        # Return custom_domain type even if tenant not found - caller decides how to handle
        return RoutingResult("custom_domain", tenant, effective_host)

    # Subdomain check (sales-agent domain with subdomain)
    subdomain = extract_subdomain_from_host(effective_host)
    tenant = get_tenant_by_subdomain(subdomain) if subdomain else None
    return RoutingResult("subdomain", tenant, effective_host)
