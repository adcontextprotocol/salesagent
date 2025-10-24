"""Configuration loader for multi-tenant setup."""

import json
import os
from contextvars import ContextVar
from typing import Any

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant


def safe_json_loads(value, default=None):
    """Safely load JSON value that might already be deserialized (SQLite vs PostgreSQL)."""
    if value is None:
        return default
    if isinstance(value, list | dict):
        # Already deserialized (SQLite)
        return value
    if isinstance(value, str):
        # JSON string (PostgreSQL)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


# Thread-safe tenant context
current_tenant: ContextVar[dict[str, Any] | None] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> dict[str, Any]:
    """Get current tenant from context."""
    tenant = current_tenant.get()
    if not tenant:
        # SECURITY: Do NOT fall back to default tenant in production.
        # This would cause tenant isolation breach.
        # Only CLI/testing scripts should call this without context.
        raise RuntimeError(
            "No tenant context set. Tenant must be set via set_current_tenant() "
            "before calling this function. This is a critical security error - "
            "falling back to default tenant would breach tenant isolation."
        )
    return tenant


def get_default_tenant() -> dict[str, Any] | None:
    """Get the default tenant for CLI/testing."""
    try:
        with get_db_session() as db_session:
            # Get first active tenant or specific default
            # Try to get 'default' tenant first, fall back to first active tenant
            stmt = select(Tenant).filter_by(tenant_id="default", is_active=True)
            tenant = db_session.scalars(stmt).first()

            if not tenant:
                # Fall back to first active tenant by creation date
                stmt = select(Tenant).filter_by(is_active=True).order_by(Tenant.created_at)
                tenant = db_session.scalars(stmt).first()

            if tenant:
                from src.core.utils.tenant_utils import serialize_tenant_to_dict

                return serialize_tenant_to_dict(tenant)
            return None
    except Exception as e:
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise


def load_config() -> dict[str, Any]:
    """
    Load configuration from current tenant.

    For backward compatibility, this returns config in the old format.
    In multi-tenant mode, config comes from database.
    """
    tenant = get_current_tenant()

    # Build config from tenant fields
    config = {
        "ad_server": {"adapter": tenant.get("ad_server", "mock"), "enabled": True},
        "creative_engine": {
            "auto_approve_formats": tenant.get("auto_approve_formats", []),
            "human_review_required": tenant.get("human_review_required", True),
        },
        "features": {
            "max_daily_budget": tenant.get("max_daily_budget", 10000),
            "enable_axe_signals": tenant.get("enable_axe_signals", True),
            "slack_webhook_url": tenant.get("slack_webhook_url"),
            "slack_audit_webhook_url": tenant.get("slack_audit_webhook_url"),
            "hitl_webhook_url": tenant.get("hitl_webhook_url"),
        },
        "admin_token": tenant.get("admin_token"),
        "dry_run": False,
    }

    # Add policy settings if present
    if tenant.get("policy_settings"):
        config["policy_settings"] = tenant["policy_settings"]

    # Apply environment variable overrides (for development/testing)
    if gemini_key := os.environ.get("GEMINI_API_KEY"):
        config["gemini_api_key"] = gemini_key

    # System-level overrides
    if dry_run := os.environ.get("ADCP_DRY_RUN"):
        config["dry_run"] = dry_run.lower() == "true"

    return config


def get_tenant_config(key: str, default=None):
    """Get config value for current tenant."""
    tenant = get_current_tenant()

    # Check if it's a top-level tenant field
    if key in tenant:
        return tenant[key]

    # Otherwise return default
    return default


def set_current_tenant(tenant_dict: dict[str, Any]):
    """Set the current tenant context."""
    current_tenant.set(tenant_dict)


def get_tenant_by_subdomain(subdomain: str) -> dict[str, Any] | None:
    """Get tenant by subdomain.

    Args:
        subdomain: The subdomain to look up (e.g., 'wonderstruck' from wonderstruck.sales-agent.scope3.com)

    Returns:
        Tenant dict if found, None otherwise
    """
    try:
        with get_db_session() as db_session:
            stmt = select(Tenant).filter_by(subdomain=subdomain, is_active=True)
            tenant = db_session.scalars(stmt).first()

            if tenant:
                from src.core.utils.tenant_utils import serialize_tenant_to_dict

                return serialize_tenant_to_dict(tenant)
            return None
    except Exception as e:
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise


def get_tenant_by_id(tenant_id: str) -> dict[str, Any] | None:
    """Get tenant by tenant_id.

    Args:
        tenant_id: The tenant_id to look up (e.g., 'tenant_wonderstruck')

    Returns:
        Tenant dict if found, None otherwise
    """
    try:
        with get_db_session() as db_session:
            stmt = select(Tenant).filter_by(tenant_id=tenant_id, is_active=True)
            tenant = db_session.scalars(stmt).first()

            if tenant:
                from src.core.utils.tenant_utils import serialize_tenant_to_dict

                return serialize_tenant_to_dict(tenant)
            return None
    except Exception as e:
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise


def get_tenant_by_virtual_host(virtual_host: str) -> dict[str, Any] | None:
    """Get tenant by virtual host."""
    from rich.console import Console
    console = Console()

    console.print(f"[blue]🔍 get_tenant_by_virtual_host called with: {virtual_host}[/blue]")
    try:
        with get_db_session() as db_session:
            stmt = select(Tenant).filter_by(virtual_host=virtual_host, is_active=True)
            console.print(f"[blue]  Executing query: {stmt}[/blue]")
            tenant = db_session.scalars(stmt).first()
            console.print(f"[blue]  Query result: {tenant}[/blue]")

            if tenant:
                from src.core.utils.tenant_utils import serialize_tenant_to_dict
                result = serialize_tenant_to_dict(tenant)
                console.print(f"[green]  ✅ Found tenant: {result.get('tenant_id')} (subdomain: {result.get('subdomain')})[/green]")
                return result
            console.print(f"[yellow]  ⚠️ No tenant found with virtual_host={virtual_host}[/yellow]")

            # Debug: Check what tenants exist
            all_tenants_stmt = select(Tenant).where(Tenant.is_active == True)
            all_tenants = db_session.scalars(all_tenants_stmt).all()
            console.print(f"[blue]  Total active tenants in database: {len(all_tenants)}[/blue]")
            for t in all_tenants:
                console.print(f"[blue]    - {t.subdomain} (virtual_host: {t.virtual_host})[/blue]")

            return None
    except Exception as e:
        console.print(f"[red]  ❌ Exception in get_tenant_by_virtual_host: {type(e).__name__}: {e}[/red]")
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise


def get_secret(key: str, default: str = None) -> str:
    """Get a secret from environment or config."""
    return os.environ.get(key, default)
