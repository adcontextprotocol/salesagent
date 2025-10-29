"""
Domain configuration utilities.

This module provides centralized domain configuration that can be customized
via environment variables, making the codebase vendor-neutral.
"""

import os


def get_base_domain() -> str:
    """Get the base domain (e.g., example.com)."""
    return os.getenv("BASE_DOMAIN", "example.com")


def get_sales_agent_domain() -> str:
    """Get the sales agent domain (e.g., sales-agent.example.com)."""
    return os.getenv("SALES_AGENT_DOMAIN", f"sales-agent.{get_base_domain()}")


def get_admin_domain() -> str:
    """Get the admin domain (e.g., admin.sales-agent.example.com)."""
    return os.getenv("ADMIN_DOMAIN", f"admin.{get_sales_agent_domain()}")


def get_super_admin_domain() -> str:
    """Get the domain for super admin emails (e.g., example.com)."""
    return os.getenv("SUPER_ADMIN_DOMAIN", get_base_domain())


def get_sales_agent_url(protocol: str = "https") -> str:
    """Get the full sales agent URL (e.g., https://sales-agent.example.com)."""
    return f"{protocol}://{get_sales_agent_domain()}"


def get_admin_url(protocol: str = "https") -> str:
    """Get the full admin URL (e.g., https://admin.sales-agent.example.com)."""
    return f"{protocol}://{get_admin_domain()}"


def get_a2a_server_url(protocol: str = "https") -> str:
    """Get the A2A server URL (e.g., https://sales-agent.example.com/a2a)."""
    return f"{get_sales_agent_url(protocol)}/a2a"


def get_mcp_server_url(protocol: str = "https") -> str:
    """Get the MCP server URL (e.g., https://sales-agent.example.com/mcp)."""
    return f"{get_sales_agent_url(protocol)}/mcp"


def is_sales_agent_domain(host: str) -> bool:
    """
    Check if the given host is part of the sales agent domain.

    Args:
        host: The hostname to check (e.g., "tenant.sales-agent.example.com")

    Returns:
        True if the host ends with the sales agent domain
    """
    return host.endswith(f".{get_sales_agent_domain()}") or host == get_sales_agent_domain()


def is_admin_domain(host: str) -> bool:
    """
    Check if the given host is the admin domain.

    Args:
        host: The hostname to check

    Returns:
        True if the host is the admin domain
    """
    return host == get_admin_domain() or host.startswith(f"{get_admin_domain()}:")


def extract_subdomain_from_host(host: str) -> str | None:
    """
    Extract the subdomain from a host if it's a sales agent domain.

    Args:
        host: The hostname (e.g., "tenant.sales-agent.example.com")

    Returns:
        The subdomain (e.g., "tenant") or None if not a subdomain
    """
    sales_domain = get_sales_agent_domain()

    if f".{sales_domain}" in host:
        return host.split(f".{sales_domain}")[0]

    return None


def get_tenant_url(subdomain: str, protocol: str = "https") -> str:
    """
    Get the URL for a specific tenant subdomain.

    Args:
        subdomain: The tenant subdomain
        protocol: The protocol (http or https)

    Returns:
        The full tenant URL (e.g., https://tenant.sales-agent.example.com)
    """
    return f"{protocol}://{subdomain}.{get_sales_agent_domain()}"


def get_oauth_redirect_uri(protocol: str = "https") -> str:
    """
    Get the OAuth redirect URI.

    Returns:
        The OAuth callback URL (e.g., https://sales-agent.example.com/admin/auth/google/callback)
    """
    # Allow override via environment variable
    env_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if env_uri:
        return env_uri

    return f"{get_sales_agent_url(protocol)}/admin/auth/google/callback"


def get_session_cookie_domain() -> str:
    """
    Get the session cookie domain (with leading dot for subdomain sharing).

    Returns:
        The cookie domain (e.g., ".sales-agent.example.com")
    """
    return f".{get_sales_agent_domain()}"
