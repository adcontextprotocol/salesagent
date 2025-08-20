"""Settings management blueprint."""

import json
import logging
import os
from datetime import UTC, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database_session import get_db_session
from models import SuperadminConfig, Tenant
from src.admin.utils import get_tenant_config_from_db, require_auth, require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
settings_bp = Blueprint("settings", __name__)


# Superadmin settings routes
@settings_bp.route("/settings")
@require_auth(admin_only=True)
def superadmin_settings():
    """Superadmin settings page."""
    with get_db_session() as db_session:
        # Get all superadmin config values
        configs = db_session.query(SuperadminConfig).all()
        config_dict = {config.config_key: config.config_value for config in configs}

        # Get environment values as fallbacks
        gam_client_id = config_dict.get("gam_oauth_client_id", os.environ.get("GAM_OAUTH_CLIENT_ID", ""))
        gam_client_secret = config_dict.get("gam_oauth_client_secret", "")  # Don't show from env for security

    return render_template(
        "settings.html",
        gam_client_id=gam_client_id,
        gam_client_secret=gam_client_secret,
    )


@settings_bp.route("/settings/update", methods=["POST"])
@require_auth(admin_only=True)
def update_superadmin_settings():
    """Update superadmin settings."""
    with get_db_session() as db_session:
        try:
            # Update GAM OAuth credentials
            gam_client_id = request.form.get("gam_oauth_client_id", "").strip()
            gam_client_secret = request.form.get("gam_oauth_client_secret", "").strip()

            # Update or create config entries
            for key, value in [
                ("gam_oauth_client_id", gam_client_id),
                ("gam_oauth_client_secret", gam_client_secret),
            ]:
                if value:  # Only update if value provided
                    config = db_session.query(SuperadminConfig).filter_by(config_key=key).first()
                    if config:
                        config.config_value = value
                        config.updated_at = datetime.now(UTC)
                    else:
                        config = SuperadminConfig(
                            config_key=key,
                            config_value=value,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                        db_session.add(config)

            db_session.commit()
            flash("Settings updated successfully", "success")

        except Exception as e:
            db_session.rollback()
            logger.error(f"Error updating settings: {e}", exc_info=True)
            flash(f"Error updating settings: {str(e)}", "error")

    return redirect(url_for("settings.superadmin_settings"))


# Tenant settings routes
@settings_bp.route("/")
@settings_bp.route("/<section>")
@require_tenant_access()
def tenant_settings(tenant_id, section=None):
    """Show tenant settings page."""
    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            flash("Tenant not found", "error")
            return redirect(url_for("index"))

        # Get tenant configuration
        config = get_tenant_config_from_db(tenant_id)

        # Get adapter info
        adapter_config = config.get("adapters", {})
        active_adapter = None
        for adapter_name, adapter_data in adapter_config.items():
            if adapter_data.get("enabled"):
                active_adapter = adapter_name
                break

        # Get available adapters
        available_adapters = ["mock", "google_ad_manager", "kevel", "triton"]

        # Get features
        features = config.get("features", {})

        # Get creative engine settings
        creative_engine = config.get("creative_engine", {})

        # Get Slack settings
        slack_webhook = tenant.slack_webhook_url or ""

        # Get GAM-specific settings if GAM is active
        gam_settings = {}
        if active_adapter == "google_ad_manager":
            gam_config = adapter_config.get("google_ad_manager", {})
            gam_settings = {
                "network_code": gam_config.get("network_code", ""),
                "refresh_token": gam_config.get("refresh_token", ""),
                "manual_approval_required": gam_config.get("manual_approval_required", False),
            }

    return render_template(
        "tenant_settings.html",
        tenant=tenant,
        tenant_id=tenant_id,
        section=section or "general",
        active_adapter=active_adapter,
        available_adapters=available_adapters,
        features=features,
        creative_engine=creative_engine,
        slack_webhook=slack_webhook,
        gam_settings=gam_settings,
        adapter_config=adapter_config,
    )


@settings_bp.route("/general", methods=["POST"])
@require_tenant_access()
def update_general(tenant_id):
    """Update general tenant settings."""
    try:
        tenant_name = request.form.get("tenant_name", "").strip()
        if not tenant_name:
            flash("Tenant name is required", "error")
            return redirect(url_for("settings.tenant_settings", tenant_id=tenant_id, section="general"))

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("index"))

            tenant.name = tenant_name
            tenant.updated_at = datetime.now(UTC)
            db_session.commit()

            flash("General settings updated successfully", "success")

    except Exception as e:
        logger.error(f"Error updating general settings: {e}", exc_info=True)
        flash(f"Error updating settings: {str(e)}", "error")

    return redirect(url_for("settings.tenant_settings", tenant_id=tenant_id, section="general"))


@settings_bp.route("/adapter", methods=["POST"])
@require_tenant_access()
def update_adapter(tenant_id):
    """Update the active adapter for a tenant."""
    try:
        new_adapter = request.form.get("adapter")
        if not new_adapter:
            flash("No adapter selected", "error")
            return redirect(url_for("settings.tenant_settings", tenant_id=tenant_id, section="adapter"))

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("index"))

            # Get current config
            if tenant.adapter_config:
                adapter_config = (
                    json.loads(tenant.adapter_config)
                    if isinstance(tenant.adapter_config, str)
                    else tenant.adapter_config
                )
            else:
                adapter_config = {}

            # Disable all adapters
            for adapter_name in adapter_config:
                if isinstance(adapter_config[adapter_name], dict):
                    adapter_config[adapter_name]["enabled"] = False

            # Enable the selected adapter
            if new_adapter not in adapter_config:
                adapter_config[new_adapter] = {}
            adapter_config[new_adapter]["enabled"] = True

            # Handle adapter-specific configuration
            if new_adapter == "google_ad_manager":
                network_code = request.form.get("gam_network_code", "").strip()
                if network_code:
                    adapter_config[new_adapter]["network_code"] = network_code

                manual_approval = request.form.get("gam_manual_approval") == "on"
                adapter_config[new_adapter]["manual_approval_required"] = manual_approval

            # Update the tenant
            tenant.adapter_config = json.dumps(adapter_config)
            tenant.ad_server = new_adapter
            tenant.updated_at = datetime.now(UTC)
            db_session.commit()

            flash(f"Adapter changed to {new_adapter}", "success")

    except Exception as e:
        logger.error(f"Error updating adapter: {e}", exc_info=True)
        flash(f"Error updating adapter: {str(e)}", "error")

    return redirect(url_for("settings.tenant_settings", tenant_id=tenant_id, section="adapter"))


@settings_bp.route("/slack", methods=["POST"])
@require_tenant_access()
def update_slack(tenant_id):
    """Update Slack integration settings."""
    try:
        webhook_url = request.form.get("slack_webhook_url", "").strip()

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("index"))

            # Update Slack webhook
            tenant.slack_webhook_url = webhook_url
            tenant.updated_at = datetime.now(UTC)
            db_session.commit()

            if webhook_url:
                flash("Slack integration updated successfully", "success")
            else:
                flash("Slack integration disabled", "info")

    except Exception as e:
        logger.error(f"Error updating Slack settings: {e}", exc_info=True)
        flash(f"Error updating Slack settings: {str(e)}", "error")

    return redirect(url_for("settings.tenant_settings", tenant_id=tenant_id, section="integrations"))
