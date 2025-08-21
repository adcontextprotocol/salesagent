"""Operations management blueprint."""

import logging

from flask import Blueprint, jsonify

from src.admin.utils import require_auth, require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
operations_bp = Blueprint("operations", __name__)


@operations_bp.route("/targeting", methods=["GET"])
@require_tenant_access()
def targeting(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/inventory", methods=["GET"])
@require_tenant_access()
def inventory(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/orders", methods=["GET"])
@require_tenant_access()
def orders(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/reporting", methods=["GET"])
@require_auth()
def reporting(tenant_id):
    """Display GAM reporting dashboard."""
    # Import needed for this function
    from flask import render_template, session

    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    # Verify tenant access
    if session.get("role") != "super_admin" and session.get("tenant_id") != tenant_id:
        return "Access denied", 403

    with get_db_session() as db_session:
        tenant_obj = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()

        if not tenant_obj:
            return "Tenant not found", 404

        # Convert to dict for template compatibility
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "ad_server": tenant_obj.ad_server,
            "subdomain": tenant_obj.subdomain,
            "is_active": tenant_obj.is_active,
        }

        # Check if tenant is using Google Ad Manager
        if tenant_obj.ad_server != "google_ad_manager":
            return (
                render_template(
                    "error.html",
                    error_title="GAM Reporting Not Available",
                    error_message=f"This tenant is currently using {tenant_obj.ad_server or 'no ad server'}. GAM Reporting is only available for tenants using Google Ad Manager.",
                    back_url=f"/tenant/{tenant_id}",
                ),
                400,
            )

        return render_template("gam_reporting.html", tenant=tenant)


@operations_bp.route("/workflows", methods=["GET"])
@require_tenant_access()
def workflows(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/media-buy/<media_buy_id>/approve", methods=["GET"])
@require_tenant_access()
def media_buy_media_buy_id_approve(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501
