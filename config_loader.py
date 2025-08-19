"""Configuration loader for multi-tenant setup."""

import json
import os
from contextvars import ContextVar
from typing import Any

from database_session import get_db_session
from models import Tenant

# Thread-safe tenant context
current_tenant: ContextVar[dict[str, Any] | None] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> dict[str, Any]:
    """Get current tenant from context."""
    tenant = current_tenant.get()
    if not tenant:
        # Fallback for CLI/testing - use default tenant
        tenant = get_default_tenant()
        if not tenant:
            raise RuntimeError("No tenant in context and no default tenant found")
    return tenant


def get_default_tenant() -> dict[str, Any] | None:
    """Get the default tenant for CLI/testing."""
    try:
        with get_db_session() as db_session:
            # Get first active tenant or specific default
            tenant = (
                db_session.query(Tenant)
                .filter_by(is_active=True)
                .order_by(db_session.query(Tenant).filter_by(tenant_id="default").exists().desc(), Tenant.created_at)
                .first()
            )

            if tenant:
                return {
                    "tenant_id": tenant.tenant_id,
                    "name": tenant.name,
                    "subdomain": tenant.subdomain,
                    "ad_server": tenant.ad_server,
                    "max_daily_budget": tenant.max_daily_budget,
                    "enable_aee_signals": tenant.enable_aee_signals,
                    "authorized_emails": json.loads(tenant.authorized_emails) if tenant.authorized_emails else [],
                    "authorized_domains": json.loads(tenant.authorized_domains) if tenant.authorized_domains else [],
                    "slack_webhook_url": tenant.slack_webhook_url,
                    "admin_token": tenant.admin_token,
                    "auto_approve_formats": (
                        json.loads(tenant.auto_approve_formats) if tenant.auto_approve_formats else []
                    ),
                    "human_review_required": tenant.human_review_required,
                    "slack_audit_webhook_url": tenant.slack_audit_webhook_url,
                    "hitl_webhook_url": tenant.hitl_webhook_url,
                    "policy_settings": json.loads(tenant.policy_settings) if tenant.policy_settings else None,
                }
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
            "enable_aee_signals": tenant.get("enable_aee_signals", True),
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


def get_secret(key: str, default: str = None) -> str:
    """Get a secret from environment or config."""
    return os.environ.get(key, default)
