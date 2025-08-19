"""API management blueprint."""

import logging

from flask import Blueprint, jsonify
from sqlalchemy import text

from database_session import get_db_session
from src.admin.utils import require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def api_health():
    """API health check endpoint."""
    try:
        with get_db_session() as db_session:
            db_session.execute(text("SELECT 1"))
            return jsonify({"status": "healthy"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy"}), 500


@api_bp.route("/gam/test-connection", methods=["POST"])
@require_tenant_access()
def gam_test_connection(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@api_bp.route("/gam/get-advertisers", methods=["POST"])
@require_tenant_access()
def gam_get_advertisers(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501
