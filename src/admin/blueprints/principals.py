"""Principals (Advertisers) management blueprint for admin UI."""

import json
import logging
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Principal, Tenant

logger = logging.getLogger(__name__)

# Create Blueprint
principals_bp = Blueprint("principals", __name__, url_prefix="/tenant/<tenant_id>")


@principals_bp.route("/principals")
@require_tenant_access()
def list_principals(tenant_id):
    """List all principals (advertisers) for a tenant."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            principals = db_session.query(Principal).filter_by(tenant_id=tenant_id).order_by(Principal.name).all()

            # Convert to dict format for template
            principals_list = []
            for principal in principals:
                # Count media buys for this principal
                media_buy_count = (
                    db_session.query(MediaBuy)
                    .filter_by(tenant_id=tenant_id, principal_id=principal.principal_id)
                    .count()
                )

                principal_dict = {
                    "principal_id": principal.principal_id,
                    "name": principal.name,
                    "access_token": principal.access_token,
                    "platform_mappings": json.loads(principal.platform_mappings) if principal.platform_mappings else {},
                    "media_buy_count": media_buy_count,
                    "created_at": principal.created_at,
                }
                principals_list.append(principal_dict)

            # The template expects this to be under the 'advertisers' key
            # since principals are advertisers in the UI
            return render_template(
                "tenant_dashboard.html",
                tenant=tenant,
                tenant_id=tenant_id,
                advertisers=principals_list,
                show_advertisers_tab=True,
            )

    except Exception as e:
        logger.error(f"Error listing principals: {e}", exc_info=True)
        flash("Error loading advertisers", "error")
        return redirect(url_for("core.index"))


@principals_bp.route("/principal/<principal_id>/update_mappings", methods=["POST"])
@require_tenant_access()
def update_mappings(tenant_id, principal_id):
    """Update principal platform mappings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        platform_mappings = data.get("platform_mappings", {})

        with get_db_session() as db_session:
            principal = db_session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=principal_id).first()

            if not principal:
                return jsonify({"error": "Principal not found"}), 404

            # Update mappings
            principal.platform_mappings = json.dumps(platform_mappings)
            principal.updated_at = datetime.now(UTC)
            db_session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "Platform mappings updated successfully",
                }
            )

    except Exception as e:
        logger.error(f"Error updating principal mappings: {e}", exc_info=True)
        return jsonify({"error": "Failed to update mappings"}), 500


@principals_bp.route("/api/gam/get-advertisers", methods=["POST"])
@require_tenant_access()
def get_gam_advertisers(tenant_id):
    """Get list of advertisers from GAM for a tenant."""
    try:
        from src.adapters.google_ad_manager import GoogleAdManager

        # Get tenant configuration
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            # Check if GAM is configured
            gam_enabled = False

            # Check multiple ways GAM might be configured
            if tenant.ad_server == "google_ad_manager":
                gam_enabled = True
            elif tenant.adapter_config and tenant.adapter_config.adapter_type == "google_ad_manager":
                gam_enabled = True

            # Debug logging to help troubleshoot
            logger.info(
                f"GAM API detection for tenant {tenant_id}: "
                f"ad_server={tenant.ad_server}, "
                f"has_adapter_config={tenant.adapter_config is not None}, "
                f"adapter_type={tenant.adapter_config.adapter_type if tenant.adapter_config else None}, "
                f"gam_enabled={gam_enabled}"
            )

            if not gam_enabled:
                logger.warning(f"GAM not enabled for tenant {tenant_id}")
                return jsonify({"error": "Google Ad Manager not configured"}), 400

            # Initialize GAM adapter with adapter config
            try:
                # Import Principal model
                from src.core.schemas import Principal

                # Create a mock principal for GAM initialization
                # Need dummy advertiser_id for GAM adapter validation, even though get_advertisers() doesn't use it
                mock_principal = Principal(
                    tenant_id=tenant_id,
                    principal_id="system",
                    name="System",
                    access_token="mock_token",
                    platform_mappings={
                        "google_ad_manager": {
                            "advertiser_id": "system_temp_advertiser_id",  # Dummy ID for validation only
                            "advertiser_name": "System (temp)",
                        }
                    },
                )

                # Build GAM config from AdapterConfig
                gam_config = (
                    {
                        "network_code": tenant.adapter_config.gam_network_code,
                        "refresh_token": tenant.adapter_config.gam_refresh_token,
                        "trafficker_id": tenant.adapter_config.gam_trafficker_id,
                        "manual_approval_required": tenant.adapter_config.gam_manual_approval_required or False,
                    }
                    if tenant.adapter_config
                    else {}
                )

                adapter = GoogleAdManager(
                    config=gam_config, principal=mock_principal, dry_run=False, tenant_id=tenant_id
                )

                # Get advertisers (companies) from GAM
                advertisers = adapter.get_advertisers()

                return jsonify(
                    {
                        "success": True,
                        "advertisers": advertisers,
                    }
                )

            except Exception as gam_error:
                logger.error(f"GAM API error: {gam_error}")
                return jsonify({"error": f"Failed to fetch advertisers: {str(gam_error)}"}), 500

    except Exception as e:
        logger.error(f"Error getting GAM advertisers: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
