"""Landing page generation for tenant-specific pages."""

import html
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _get_jinja_env() -> Environment:
    """Get configured Jinja2 environment for landing page templates."""
    template_dir = os.path.join(os.path.dirname(__file__), "templates")

    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _determine_base_url(virtual_host: str | None = None) -> str:
    """Determine the base URL for the current environment.

    Args:
        virtual_host: Virtual host if provided (e.g., from Apx-Incoming-Host header)

    Returns:
        Base URL for generating endpoint URLs
    """
    # Check if we're in production
    if os.getenv("PRODUCTION") == "true":
        if virtual_host:
            return f"https://{virtual_host}"
        # Fallback to production domain
        return "https://sales-agent.scope3.com"

    # Check for virtual host in development
    if virtual_host:
        # Development with virtual host
        return f"https://{virtual_host}"

    # Local development fallback
    port = os.getenv("ADCP_SALES_PORT", "8080")
    return f"http://localhost:{port}"


def _extract_tenant_subdomain(tenant: dict, virtual_host: str | None = None) -> str | None:
    """Extract tenant subdomain from tenant data or virtual host.

    Args:
        tenant: Tenant data from database
        virtual_host: Virtual host domain if available

    Returns:
        Tenant subdomain if determinable
    """
    # First try virtual host
    if virtual_host:
        # Extract subdomain from virtual host (e.g., scribd.sales-agent.scope3.com -> scribd)
        if ".sales-agent.scope3.com" in virtual_host:
            return virtual_host.split(".sales-agent.scope3.com")[0]
        elif "." in virtual_host:
            # Generic virtual host, use first part
            return virtual_host.split(".")[0]

    # Fallback to tenant subdomain field
    if tenant.get("subdomain"):
        return tenant["subdomain"]

    # Fallback to tenant_id
    return tenant.get("tenant_id")


def generate_tenant_landing_page(tenant: dict, virtual_host: str | None = None) -> str:
    """Generate HTML content for tenant landing page.

    Args:
        tenant: Tenant data from database containing name, subdomain, etc.
        virtual_host: Virtual host domain if applicable (e.g., from Apx-Incoming-Host)

    Returns:
        Complete HTML page as string

    Raises:
        Exception: If template rendering fails
    """
    # Get base URL for this environment
    base_url = _determine_base_url(virtual_host)

    # Extract tenant subdomain
    tenant_subdomain = _extract_tenant_subdomain(tenant, virtual_host)

    # Generate endpoint URLs
    mcp_url = f"{base_url}/mcp"
    a2a_url = f"{base_url}/a2a"
    agent_card_url = f"{base_url}/.well-known/agent.json"
    admin_url = f"{base_url}/admin/"

    # Prepare template context
    template_context = {
        # Tenant information (escaped by Jinja2 auto-escape)
        "tenant_name": tenant.get("name", "Unknown Publisher"),
        "tenant_subdomain": tenant_subdomain,
        # URLs
        "base_url": base_url,
        "mcp_url": mcp_url,
        "a2a_url": a2a_url,
        "agent_card_url": agent_card_url,
        "admin_url": admin_url,
        "adcp_docs_url": "https://adcontextprotocol.org",
        "scope3_url": "https://scope3.com",
        # Virtual host info
        "virtual_host": virtual_host,
        "is_production": os.getenv("PRODUCTION") == "true",
        # Additional context
        "page_title": f"{tenant.get('name', 'Publisher')} Sales Agent",
    }

    # Load and render template
    env = _get_jinja_env()
    template = env.get_template("tenant_landing.html")

    return template.render(**template_context)


def generate_fallback_landing_page(error_message: str = "Tenant not found") -> str:
    """Generate a fallback landing page when tenant lookup fails.

    Args:
        error_message: Error message to display

    Returns:
        Simple HTML error page
    """
    # Simple fallback HTML without template
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>AdCP Sales Agent</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 2rem;
            }}
            .container {{
                background: white;
                border-radius: 8px;
                padding: 2rem;
                max-width: 500px;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            h1 {{ color: #e74c3c; }}
            .admin-link {{
                display: inline-block;
                background: #007bff;
                color: white;
                padding: 0.75rem 1.5rem;
                border-radius: 4px;
                text-decoration: none;
                margin-top: 1rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AdCP Sales Agent</h1>
            <p>{html.escape(error_message)}</p>
            <p>Please check the URL or contact your administrator.</p>
            <a href="/admin/" class="admin-link">Go to Admin Dashboard</a>
        </div>
    </body>
    </html>
    """
