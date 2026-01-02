"""
Domain configuration utilities.

This module provides centralized domain configuration that can be customized
via environment variables, making the codebase vendor-neutral.

In single-tenant mode, most of these functions are not needed since there's
no subdomain routing. In multi-tenant mode, you must set SALES_AGENT_DOMAIN.
"""

import os


def get_sales_agent_domain() -> str | None:
    """Get the sales agent domain (e.g., sales-agent.example.com).

    Returns:
        The configured SALES_AGENT_DOMAIN, or None if not configured.
        Multi-tenant mode requires this to be set.
    """
    return os.getenv("SALES_AGENT_DOMAIN")


def get_admin_domain() -> str | None:
    """Get the admin domain (e.g., admin.sales-agent.example.com).

    Returns:
        The configured ADMIN_DOMAIN, or constructs from SALES_AGENT_DOMAIN,
        or None if neither is configured.
    """
    # First check for explicit ADMIN_DOMAIN
    if domain := os.getenv("ADMIN_DOMAIN"):
        return domain
    # Fall back to constructing from sales agent domain if available
    if sales_domain := get_sales_agent_domain():
        return f"admin.{sales_domain}"
    return None


def get_super_admin_domain() -> str | None:
    """Get the domain for super admin emails (e.g., example.com).

    Returns:
        The configured SUPER_ADMIN_DOMAIN, or None if not configured.
    """
    return os.getenv("SUPER_ADMIN_DOMAIN")


def get_sales_agent_url(protocol: str = "https") -> str | None:
    """Get the full sales agent URL (e.g., https://sales-agent.example.com).

    Returns:
        The full URL, or None if SALES_AGENT_DOMAIN is not configured.
    """
    if domain := get_sales_agent_domain():
        return f"{protocol}://{domain}"
    return None


def get_admin_url(protocol: str = "https") -> str | None:
    """Get the full admin URL (e.g., https://admin.sales-agent.example.com).

    Returns:
        The full URL, or None if domain is not configured.
    """
    if domain := get_admin_domain():
        return f"{protocol}://{domain}"
    return None


def get_a2a_server_url(protocol: str = "https") -> str | None:
    """Get the A2A server URL (e.g., https://sales-agent.example.com/a2a).

    Returns:
        The full URL, or None if SALES_AGENT_DOMAIN is not configured.
    """
    if url := get_sales_agent_url(protocol):
        return f"{url}/a2a"
    return None


def get_mcp_server_url(protocol: str = "https") -> str | None:
    """Get the MCP server URL (e.g., https://sales-agent.example.com/mcp).

    Returns:
        The full URL, or None if SALES_AGENT_DOMAIN is not configured.
    """
    if url := get_sales_agent_url(protocol):
        return f"{url}/mcp"
    return None


def is_sales_agent_domain(host: str) -> bool:
    """
    Check if the given host is part of the sales agent domain.

    Args:
        host: The hostname to check (e.g., "tenant.sales-agent.example.com")

    Returns:
        True if the host ends with the sales agent domain.
        Returns False if SALES_AGENT_DOMAIN is not configured.
    """
    sales_domain = get_sales_agent_domain()
    if not sales_domain:
        return False
    return host.endswith(f".{sales_domain}") or host == sales_domain


def get_admin_domains() -> list[str]:
    """Get all configured admin domains.

    Returns a list of admin domains from:
    1. ADMIN_DOMAINS env var (comma-separated list of additional admin domains)
    2. ADMIN_DOMAIN env var (single primary admin domain)
    3. Constructed from SALES_AGENT_DOMAIN (admin.{sales_agent_domain})

    Returns:
        List of admin domains, may be empty if none configured.
    """
    domains = []

    # Check for explicit multiple admin domains
    if admin_domains := os.getenv("ADMIN_DOMAINS"):
        domains.extend([d.strip() for d in admin_domains.split(",") if d.strip()])

    # Add primary admin domain if configured and not already in list
    if primary := get_admin_domain():
        if primary not in domains:
            domains.append(primary)

    return domains


def is_admin_domain(host: str) -> bool:
    """
    Check if the given host is an admin domain.

    Args:
        host: The hostname to check

    Returns:
        True if the host is one of the configured admin domains.
        Returns False if no admin domains are configured.
    """
    admin_domains = get_admin_domains()
    if not admin_domains:
        return False

    # Check against all configured admin domains
    for admin_domain in admin_domains:
        if host == admin_domain or host.startswith(f"{admin_domain}:"):
            return True

    return False


def extract_subdomain_from_host(host: str) -> str | None:
    """
    Extract the subdomain from a host if it's a sales agent domain.

    Args:
        host: The hostname (e.g., "tenant.sales-agent.example.com")

    Returns:
        The subdomain (e.g., "tenant") or None if not a subdomain
        or if SALES_AGENT_DOMAIN is not configured.
    """
    sales_domain = get_sales_agent_domain()
    if not sales_domain:
        return None

    if f".{sales_domain}" in host:
        return host.split(f".{sales_domain}")[0]

    return None


def get_tenant_url(subdomain: str, protocol: str = "https") -> str | None:
    """
    Get the URL for a specific tenant subdomain.

    Args:
        subdomain: The tenant subdomain
        protocol: The protocol (http or https)

    Returns:
        The full tenant URL (e.g., https://tenant.sales-agent.example.com)
        or None if SALES_AGENT_DOMAIN is not configured.
    """
    if sales_domain := get_sales_agent_domain():
        return f"{protocol}://{subdomain}.{sales_domain}"
    return None


def get_oauth_redirect_uri(protocol: str = "https") -> str | None:
    """
    Get the OAuth redirect URI.

    Returns:
        The OAuth callback URL (e.g., https://sales-agent.example.com/admin/auth/google/callback)
        or None if not configured.
    """
    # Allow override via environment variable
    if env_uri := os.getenv("GOOGLE_OAUTH_REDIRECT_URI"):
        return env_uri

    if url := get_sales_agent_url(protocol):
        return f"{url}/admin/auth/google/callback"
    return None


def get_session_cookie_domain() -> str | None:
    """
    Get the session cookie domain (with leading dot for subdomain sharing).

    Returns:
        The cookie domain (e.g., ".sales-agent.example.com")
        or None if SALES_AGENT_DOMAIN is not configured.
    """
    if sales_domain := get_sales_agent_domain():
        return f".{sales_domain}"
    return None
