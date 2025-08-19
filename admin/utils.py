"""Utility functions shared across admin UI modules."""

import json
import logging
import os
from functools import wraps

from flask import abort, g, jsonify, redirect, session, url_for

from database_session import get_db_session
from models import SuperadminConfig, Tenant, User

logger = logging.getLogger(__name__)


def parse_json_config(config_str):
    """Parse JSON config string."""
    if not config_str:
        return {}
    try:
        return json.loads(config_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def get_tenant_config_from_db(tenant_id):
    """Get tenant configuration from database.

    Args:
        tenant_id: The tenant ID to fetch config for

    Returns:
        dict: The tenant configuration with adapter settings, features, etc.
    """
    if not tenant_id:
        logger.warning("get_tenant_config_from_db called with empty tenant_id")
        return {}

    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                logger.warning(f"Tenant not found: {tenant_id}")
                return {}

            # Build config from individual columns
            config = {
                "adapters": {},
                "features": {},
                "creative_engine": {},
                "admin_token": tenant.admin_token or "",
                "slack_webhook_url": tenant.slack_webhook_url or "",
                "policy_settings": {},
            }

            # Add adapter config if it exists
            if tenant.adapter_config:
                adapter_config = parse_json_config(tenant.adapter_config)
                if adapter_config:
                    config["adapters"] = adapter_config

            # Add features config
            if tenant.features_config:
                features_config = parse_json_config(tenant.features_config)
                if features_config:
                    config["features"] = features_config

            # Add creative engine config
            if tenant.creative_engine_config:
                creative_config = parse_json_config(tenant.creative_engine_config)
                if creative_config:
                    config["creative_engine"] = creative_config

            # Add policy settings
            if tenant.policy_settings:
                policy_settings = parse_json_config(tenant.policy_settings)
                if policy_settings:
                    config["policy_settings"] = policy_settings

            return config

    except Exception as e:
        logger.error(f"Error getting tenant config: {e}")
        return {}


def is_super_admin(email):
    """Check if user is a super admin based on email or domain."""
    if not email:
        return False

    # Check database for super admin configuration
    try:
        with get_db_session() as db_session:
            # Check exact emails
            emails_config = db_session.query(SuperadminConfig).filter_by(config_key="super_admin_emails").first()
            if emails_config and emails_config.config_value:
                emails_list = [e.strip().lower() for e in emails_config.config_value.split(",")]
                if email.lower() in emails_list:
                    return True

            # Check domains
            domains_config = db_session.query(SuperadminConfig).filter_by(config_key="super_admin_domains").first()
            if domains_config and domains_config.config_value:
                domains_list = [d.strip().lower() for d in domains_config.config_value.split(",")]
                email_domain = email.split("@")[1].lower() if "@" in email else ""
                if email_domain in domains_list:
                    return True

    except Exception as e:
        logger.error(f"Error checking super admin status: {e}")

    return False


def is_tenant_admin(email, tenant_id=None):
    """Check if user is a tenant admin.

    Args:
        email: User's email address
        tenant_id: Optional tenant ID to check admin status for specific tenant

    Returns:
        bool: True if user is a tenant admin
    """
    if not email:
        return False

    # Super admins are implicitly tenant admins
    if is_super_admin(email):
        return True

    # Check if user is a tenant admin in the database
    try:
        with get_db_session() as db_session:
            query = db_session.query(User).filter_by(email=email.lower(), is_active=True, is_admin=True)

            if tenant_id:
                # Check for specific tenant
                query = query.filter_by(tenant_id=tenant_id)

            return query.first() is not None

    except Exception as e:
        logger.error(f"Error checking tenant admin status: {e}")
        return False

    return False


def require_auth(admin_only=False):
    """Decorator to require authentication for routes."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for test mode
            test_mode = os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true"
            if test_mode and "test_user" in session:
                g.user = session["test_user"]
                return f(*args, **kwargs)

            if "user" not in session:
                return redirect(url_for("login"))

            # Store user in g for access in view functions
            g.user = session["user"]

            # Check admin requirement
            if admin_only and not is_super_admin(session["user"]):
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_tenant_access(api_mode=False):
    """Decorator to require tenant access for routes."""

    def decorator(f):
        @wraps(f)
        def decorated_function(tenant_id, *args, **kwargs):
            # Check for test mode
            test_mode = os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true"
            if test_mode and "test_user" in session:
                g.user = session["test_user"]
                # Test users can access their assigned tenant
                if "test_tenant_id" in session and session["test_tenant_id"] == tenant_id:
                    return f(tenant_id, *args, **kwargs)
                # Super admins can access all tenants
                if session.get("test_user_role") == "super_admin":
                    return f(tenant_id, *args, **kwargs)

            if "user" not in session:
                if api_mode:
                    return jsonify({"error": "Authentication required"}), 401
                return redirect(url_for("login"))

            email = session["user"]

            # Super admins have access to all tenants
            if is_super_admin(email):
                return f(tenant_id, *args, **kwargs)

            # Check if user has access to this specific tenant
            try:
                with get_db_session() as db_session:
                    user = (
                        db_session.query(User)
                        .filter_by(email=email.lower(), tenant_id=tenant_id, is_active=True)
                        .first()
                    )

                    if not user:
                        if api_mode:
                            return jsonify({"error": "Access denied"}), 403
                        abort(403)

                    return f(tenant_id, *args, **kwargs)

            except Exception as e:
                logger.error(f"Error checking tenant access: {e}")
                if api_mode:
                    return jsonify({"error": "Internal server error"}), 500
                abort(500)

        return decorated_function

    return decorator


def validate_gam_network_response(network):
    """Validate GAM network API response structure."""
    if not network:
        return False, "Network response is empty"

    # Check required fields
    required_fields = ["networkCode", "displayName", "id"]
    for field in required_fields:
        if field not in network:
            return False, f"Missing required field: {field}"

    # Validate field types
    try:
        int(network["networkCode"])
        int(network["id"])
    except (ValueError, TypeError):
        return False, "Network code and ID must be numeric"

    if not isinstance(network["displayName"], str):
        return False, "Display name must be a string"

    return True, None


def validate_gam_user_response(user):
    """Validate GAM user API response structure."""
    if not user:
        return False, "User response is empty"

    # Check required fields
    if "id" not in user:
        return False, "Missing user ID"

    # Validate ID is numeric
    try:
        int(user["id"])
    except (ValueError, TypeError):
        return False, "User ID must be numeric"

    return True, None


def get_custom_targeting_mappings(tenant_id=None):
    """Get custom targeting key mappings for a tenant."""
    mappings = {}

    if tenant_id:
        try:
            with get_db_session() as db_session:
                tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
                if tenant and tenant.features_config:
                    features = parse_json_config(tenant.features_config)
                    if isinstance(features, dict) and "custom_targeting_mappings" in features:
                        mappings = features["custom_targeting_mappings"]
        except Exception as e:
            logger.error(f"Error getting custom targeting mappings: {e}")

    return mappings


def translate_custom_targeting(custom_targeting_node, tenant_id=None):
    """Translate GAM custom targeting to human-readable format."""
    if not custom_targeting_node:
        return {}

    # Get tenant-specific mappings
    mappings = get_custom_targeting_mappings(tenant_id)

    result = {}

    # Handle children (nested targeting)
    if hasattr(custom_targeting_node, "children") and custom_targeting_node.children:
        for child in custom_targeting_node.children:
            child_result = translate_custom_targeting(child, tenant_id)
            result.update(child_result)

    # Handle direct attributes
    if hasattr(custom_targeting_node, "keyId") and hasattr(custom_targeting_node, "valueIds"):
        key_id = str(custom_targeting_node.keyId)

        # Use mapping if available, otherwise use the ID
        key_name = mappings.get(key_id, f"custom_key_{key_id}")

        # Get the operator (default to "equals" if not specified)
        operator = getattr(custom_targeting_node, "operator", "IS")

        # Store value IDs
        if custom_targeting_node.valueIds:
            result[key_name] = {"operator": operator, "values": list(custom_targeting_node.valueIds)}

    return result
