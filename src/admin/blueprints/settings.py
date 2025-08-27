"""Settings management blueprint.

⚠️ ROUTING NOTICE: This file handles SUPERADMIN settings only!
- URL: /admin/settings
- Function: superadmin_settings()  
- The tenant_settings() function in this file is UNUSED - actual tenant settings 
  are handled by src/admin/blueprints/tenants.py::settings()
"""

import logging
import os
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.admin.utils import get_tenant_config_from_db, require_auth, require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import SuperadminConfig, Tenant

logger = logging.getLogger(__name__)

# Create blueprints - separate for superadmin and tenant settings
superadmin_settings_bp = Blueprint("superadmin_settings", __name__)
settings_bp = Blueprint("settings", __name__)


# Superadmin settings routes
@superadmin_settings_bp.route("/settings")
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

    # Format config_items as expected by template
    config_items = {
        "gam_oauth_client_id": {"value": gam_client_id, "description": "OAuth 2.0 Client ID from Google Cloud Console"},
        "gam_oauth_client_secret": {
            "value": gam_client_secret,
            "description": "OAuth 2.0 Client Secret (stored securely)",
        },
    }

    return render_template(
        "settings.html",
        config_items=config_items,
        gam_client_id=gam_client_id,
        gam_client_secret=gam_client_secret,
    )


@superadmin_settings_bp.route("/settings/update", methods=["POST"])
@require_auth(admin_only=True)
def update_admin_settings():
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

    return redirect(url_for("superadmin_settings.superadmin_settings"))


# POST-only routes for updating tenant settings
# GET requests for settings are handled by src/admin/blueprints/tenants.py::settings()


@settings_bp.route("/general", methods=["POST"])
@require_tenant_access()
def update_general(tenant_id):
    """Update general tenant settings."""
    try:
        # Get the tenant name from the form field named "name"
        tenant_name = request.form.get("name", "").strip()

        if not tenant_name:
            flash("Tenant name is required", "error")
            return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="general"))

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Update tenant with form data
            tenant.name = tenant_name

            # Update other fields if they exist
            if "max_daily_budget" in request.form:
                try:
                    tenant.max_daily_budget = int(request.form.get("max_daily_budget", 10000))
                except ValueError:
                    tenant.max_daily_budget = 10000

            if "enable_aee_signals" in request.form:
                tenant.enable_aee_signals = request.form.get("enable_aee_signals") == "on"
            else:
                tenant.enable_aee_signals = False

            if "human_review_required" in request.form:
                tenant.human_review_required = request.form.get("human_review_required") == "on"
            else:
                tenant.human_review_required = False

            tenant.updated_at = datetime.now(UTC)
            db_session.commit()

            flash("General settings updated successfully", "success")

    except Exception as e:
        logger.error(f"Error updating general settings: {e}", exc_info=True)
        flash(f"Error updating settings: {str(e)}", "error")

    return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="general"))


@settings_bp.route("/adapter", methods=["POST"])
@require_tenant_access()
def update_adapter(tenant_id):
    """Update the active adapter for a tenant."""
    try:
        # Support both JSON (from our frontend) and form data (from tests)
        if request.is_json:
            new_adapter = request.json.get("adapter")
        else:
            new_adapter = request.form.get("adapter")

        if not new_adapter:
            if request.is_json:
                return jsonify({"success": False, "error": "No adapter selected"}), 400
            flash("No adapter selected", "error")
            return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="adapter"))

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                if request.is_json:
                    return jsonify({"success": False, "error": "Tenant not found"}), 404
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Update or create adapter config
            adapter_config_obj = tenant.adapter_config
            if adapter_config_obj:
                # Update existing config
                adapter_config_obj.adapter_type = new_adapter
            else:
                # Create new config
                from src.core.database.models import AdapterConfig

                adapter_config_obj = AdapterConfig(tenant_id=tenant_id, adapter_type=new_adapter)
                db_session.add(adapter_config_obj)

            # Handle adapter-specific configuration
            if new_adapter == "google_ad_manager":
                if request.is_json:
                    network_code = (
                        request.json.get("gam_network_code", "").strip() if request.json.get("gam_network_code") else ""
                    )
                    manual_approval = request.json.get("gam_manual_approval", False)
                else:
                    network_code = request.form.get("gam_network_code", "").strip()
                    manual_approval = request.form.get("gam_manual_approval") == "on"

                if network_code:
                    adapter_config_obj.gam_network_code = network_code
                adapter_config_obj.gam_manual_approval_required = manual_approval
            elif new_adapter == "mock":
                if request.is_json:
                    dry_run = request.json.get("mock_dry_run", False)
                else:
                    dry_run = request.form.get("mock_dry_run") == "on"
                adapter_config_obj.mock_dry_run = dry_run

            # Update the tenant
            tenant.ad_server = new_adapter
            tenant.updated_at = datetime.now(UTC)
            db_session.commit()

            # Return appropriate response based on request type
            if request.is_json:
                return jsonify({"success": True, "message": f"Adapter changed to {new_adapter}"}), 200

            flash(f"Adapter changed to {new_adapter}", "success")
            return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="adapter"))

    except Exception as e:
        logger.error(f"Error updating adapter: {e}", exc_info=True)

        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400

        flash(f"Error updating adapter: {str(e)}", "error")
        return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="adapter"))


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
                return redirect(url_for("core.index"))

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

    return redirect(url_for("tenants.tenant_settings", tenant_id=tenant_id, section="integrations"))
